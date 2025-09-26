import asyncio
import websockets
import json
import subprocess
import os
import pyautogui
from Xlib.display import Display
from Xlib.ext.xtest import fake_input
from Xlib import X, display
import time
from PIL import Image
import base64
import ssl
import cv2
import numpy as np
from command_executor import CommandExecutor

#x11-apps

WEBSOCKET_URI = "wss://localhost:3033"
VIRTUAL_DISPLAY = ":3"
SCREEN_SIZE = "1920x1080"
BROWSER_URL = "https://web.telegram.org"
WORKER_NAME = "desktop-1"

SCREENSHOT_INTERVAL = 1
SCREEN_RESOLUTION = SCREEN_SIZE + "x24"
CHROME_DATA_DIR = "./userdata/" + WORKER_NAME

os.environ['DISPLAY'] = VIRTUAL_DISPLAY
#os.environ['__GL_SYNC_TO_VBLANK'] = '1'
#os.environ['__GL_MAX_FRAMES_ALLOWED'] = '3'

xvfb_process = None
chrome_process = None
executor = None

last_click = [0, 0]

def cleanup():
    """Убиваем все зависимые процессы"""
    subprocess.run(["pkill", "-f", f"Xvfb {VIRTUAL_DISPLAY}"])
    subprocess.run(["pkill", "-f", "chrome.*--display"])
    print("Процессы очищены")

def start_virtual_display():
    """Запуск виртуального экрана с гарантированной изоляцией"""
    global xvfb_process
    cleanup()
    xvfb_process = subprocess.Popen(
        [
            "Xvfb", VIRTUAL_DISPLAY,
            "-screen", "0", SCREEN_RESOLUTION,
            "-ac",
            "-noreset"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={}
    )
    for _ in range(10):
        try:
            # Проверяем доступность экрана через xdpyinfo
            subprocess.check_call(
                ["xdpyinfo", "-display", VIRTUAL_DISPLAY],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"[Xvfb] Виртуальный экран {VIRTUAL_DISPLAY} готов")
            return True
        except:
            time.sleep(0.5)
    print("[Xvfb] Ошибка инициализации")
    return False

def start_browser():
    """Запуск Chrome строго на виртуальном экране"""
    global chrome_process
    chrome_process = subprocess.Popen(
        [
            "cpulimit",
            "google-chrome",
            "-l", "5", "--",
            f"--display={VIRTUAL_DISPLAY}",
            "--start-fullscreen",
            #"--kiosk",
            "--no-first-run",
            #"--disable-gpu",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-gpu-compositing",
            "--disable-gpu-vsync",
            "--disable-frame-rate-limit",
            "--disable-gpu-driver-bug-workarounds",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-accelerated-video-decode",
            "--disable-accelerated-video-encode",
            "--disable-accelerated-2d-canvas",
            "--disable-3d-apis",
            "--disable-webgl",
            "--disable-webgl2",
            "--disable-breakpad",
            "--disable-logging",
            "--mute-audio",
            "--window-size=800,800",
            "--no-sandbox",
            f"--user-data-dir={CHROME_DATA_DIR}",
            BROWSER_URL
        ],
        env={
            "DISPLAY": VIRTUAL_DISPLAY,
            "XAUTHORITY": "/dev/null",  # Блокируем доступ к основному X-серверу
            **os.environ
        }
    )
    print("[Chrome] Браузер запущен на виртуальном экране")

async def get_chrome_window():
    """Находит размер и позицию окна Chrome"""
    try:
        output = subprocess.check_output(
            ["xwininfo", "-root", "-tree", "-display", VIRTUAL_DISPLAY],
            universal_newlines=True
        )
        for line in output.splitlines():
            if "Google Chrome" in line or "chromium" in line.lower():
                parts = line.split()
                for part in parts:
                    if "x" in part and "+" in part:
                        size, pos = part.split("+")
                        return tuple(map(int, size.split("x"))) + tuple(map(int, pos.split("+")))
        return (1920, 1080, 0, 0)
    except Exception as e:
        print(f"[Window Info] Ошибка: {e}")
        return (1920, 1080, 0, 0)

async def capture_screenshot():
    """Надежный метод захвата скриншота"""
    screenshot_path = "/tmp/screenshot.png"
    optimized_path = "/tmp/optimized.png"
    #if os.path.exists(screenshot_path):
    #    os.remove(screenshot_path)
    subprocess.run([
        "scrot",
        "-o",
        "-p",
        screenshot_path,
    ], env=dict(DISPLAY=VIRTUAL_DISPLAY), check=True),
    
    #command = [
    #    "ffmpeg",
    #    "-loglevel", "quiet",
    #    "-f", "x11grab",
    #    "-i", VIRTUAL_DISPLAY + '.0',
    #    "-frames:v", "1",
    #    "-update", "1",
    #    "-y",
    #    screenshot_path
    #]
    #subprocess.run(command, check=True)
    
    # Проверка что скриншот не черный
    img = Image.open(screenshot_path)
    #if img.getextrema()[0] == (0, 0):  # Все пиксели черные
    #    raise ValueError("Черный скриншот")
    img.convert("P", palette=Image.ADAPTIVE).save(optimized_path, optimize=True)
        
    return optimized_path

async def send_screenshot(ws):
    path = await capture_screenshot()
    
    with open(path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    os.remove(path)
    
    await ws.send(json.dumps({
        "action": "screenshot",
        "data": image_data,
        "timestamp": int(time.time())
    }))
    
    print(f"[Screenshot] Отправлен ({len(image_data)} байт)")

async def screenshot_loop(ws):
    while True:
        start_time = time.time()
        await send_screenshot(ws)
        elapsed = time.time() - start_time # задержка 1 сек.
        await asyncio.sleep(max(0, SCREENSHOT_INTERVAL - elapsed))

def locate_image(template_path, screenshot=None, threshold=0.8, method='TM_CCOEFF_NORMED'):
    """Поиск шаблона на изображении с использованием template matching"""
    try:
        if screenshot is None:
            screenshot = cv2.imread("/tmp/screenshot.png", cv2.IMREAD_COLOR)
        template = cv2.imread("images/" + template_path, cv2.IMREAD_COLOR)
        
        if screenshot is None:
            print("Не удалось загрузить скриншот")
            return None
        if template is None:
            print(f"Не удалось загрузить шаблон: {template_path}")
            return None
            
        # Преобразование в grayscale для лучшей производительности
        screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        # Получаем размеры шаблона
        w, h = template_gray.shape[::-1]
        
        # Выполняем template matching
        res = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        print(max_val)
        # Если совпадение достаточно хорошее
        if max_val >= threshold:
            top_left = max_loc
            bottom_right = (top_left[0] + w, top_left[1] + h)
            midX = int(bottom_right[0] - (bottom_right[0] - top_left[0]) / 2)
            midY = int(bottom_right[1] - (bottom_right[1] - top_left[1]) / 2)
            return [midX, midY]
        
        return None
    except Exception as e:
        print(f"Ошибка в locateOnScreen: {e}")
        return None

async def start(ws):
    global executor
    executor = CommandExecutor(
        click_func=click,
        locate_func=locate_image,
        min_delay=1.0,
        max_delay=2.0,
        cycle_min_delay=2.0,
        cycle_max_delay=5.0
    )
    
    async def no_image(path):
        await ws.send(json.dumps({
            "action": "seq_status",
            "data": {
                "result": "error",
                "image": path        
            }
        }))

    async def success(attempt):
        await ws.send(json.dumps({
            "action": "seq_status",
            "data": {
                "result": "success",
                "attempt": attempt        
            }
        }))
    
    executor.add_hook("no_image", no_image)
    executor.add_hook("success", success)
    
    popups = True
    while popups:
        popup = locate_image("close_popup.png")
        print(popup)
        if popup:
            click(popup[0], popup[1])
        else:
            popups = False
        await asyncio.sleep(1)
    
    # Пример скрипта
    script = """
    click(avatar.png)
    cycle start
    click(user_menu.png)
    click(gift_ico.png)
    wait(1)
    click(rare_gifts_EN.png)
    check(previous_gifts_look.png)
    click(close.png)
    cycle end
    """
    
    task = asyncio.create_task(executor.run_script(script))
    print("starting")
    await task
    
    executor = None
    
    await ws.send(json.dumps({
        "action": "seq_status",
        "data": {
            "result": "stopped"   
        }
    }))

async def command_handler(ws):
    """Обработчик других команд"""
    while True:
        try:
            message = await ws.recv()
            command = json.loads(message)
            print(f"Получена команда: {command}")
            #print(locateOnScreen("menu.png"))

            if command.get("status") == "rejected":
                raise Exception("rejected")
            if command.get("status") == "approved":
                start_browser()
                await asyncio.sleep(25)
                await start(ws)
            
            if command.get("action") == "save":
                buffer, name = command["buffer"], command["name"]
                img_data = base64.b64decode(buffer)
                with open(name, "wb") as f:
                    f.write(img_data)
            
            if command.get("action") == "click_image":
                name = command["name"]
                location = locate_image(name, threshold=0.8)
                print(location)
                if location:
                    print("Объект найден:", location)
                    
                    click(location[0], location[1])
                else:
                    print("Объект не найден")
            
            if command.get("action") == "start":
                await start(ws)
            if command.get("action") == "stop":
                global executor
                if executor != None:
                    await executor.stop()
                    executor = None
            if command.get("action") == "click":
                x, y = command["x"], command["y"]
                click(x, y)
                print('clicked')
            if command.get("action") == "buy_gift":
                id = command("id")

        except websockets.exceptions.ConnectionClosed:
            print("Соединение закрыто")
            break
        except Exception as e:
            print(f"Ошибка обработки команды: {e}")

def click(x, y):
    d = Display(VIRTUAL_DISPLAY)
    fake_input(d, X.MotionNotify, x=x, y=y)
    fake_input(d, X.ButtonPress, 1)
    fake_input(d, X.ButtonRelease, 1)
    d.sync()
    last_click = [x, y]
    return True

async def websocket_client():
    """WebSocket-клиент с управлением браузером"""
    print(f"[WebSocket] Подключение к {WEBSOCKET_URI}")
    
    client_cert = './https/client.crt'
    client_key = './https/client.key'
    ca_cert = './https/ca.crt'
    
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.load_cert_chain(certfile=client_cert, keyfile=client_key)
    ssl_context.load_verify_locations(cafile=ca_cert) 
    ssl_context.check_hostname = False
    
    retries = 0
    
    while True:
        try:
            async with websockets.connect(WEBSOCKET_URI, ssl=ssl_context) as ws:
                 await ws.send(json.dumps({ "status": "ready", "name": WORKER_NAME, "properties": { "screen": SCREEN_SIZE } }))
                 await asyncio.gather(
                    screenshot_loop(ws),
                    command_handler(ws)
                 )
        except Exception as e:
            global executor
            print(f"Ошибка: {e}, переподключение...")
            if executor != None:
                    await executor.stop()
                    executor = None
            retries += 1
            if retries < 5:
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(3)

async def main():
    if not start_virtual_display():
        return
    
    await websocket_client()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        cleanup()
