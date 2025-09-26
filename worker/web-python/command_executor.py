import re
import time
import random
from typing import List, Dict, Optional, Callable, Any
import asyncio

class CommandExecutor:
    def __init__(self, 
                 click_func: Callable[[str], bool] = None,
                 locate_func: Callable[[str], Any] = None,
                 default_timeout: float = 4.0,
                 min_delay: float = 0.7,
                 max_delay: float = 1.5,
                 cycle_min_delay: float = 2.0,
                 cycle_max_delay: float = 5.0):
        
        self._hooks = {
            'success': [],
            'no_image': [],
        }
        
        self.click_func = click_func
        self.locate_func = locate_func
        self.default_timeout = default_timeout
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.cycle_min_delay = cycle_min_delay
        self.cycle_max_delay = cycle_max_delay
        self.cycle_commands = []
        self.in_cycle = False
        self._is_running = False
        self._current_script = None
        self._stop_requested = False
        self._queue = asyncio.Queue()

    def add_hook(self, event: str, callback: Callable):
        """Добавляет обработчик события"""
        if event in self._hooks:
            self._hooks[event].append(callback)
        else:
            raise ValueError(f"Unknown event type: {event}")
    
    async def _trigger_hook(self, event: str, *args, **kwargs):
        """Вызывает все обработчики для указанного события"""
        for callback in self._hooks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                print(f"Error in {event} hook: {e}")

    def parse_commands(self, script: str) -> List[Dict]:
        """Парсит скрипт и возвращает список команд"""
        commands = []
        lines = [line.strip() for line in script.split('\n') if line.strip()]
        
        for line in lines:
            if line.lower() == 'cycle start':
                self.in_cycle = True
                self.cycle_commands = []
            elif line.lower() == 'cycle end':
                self.in_cycle = False
                commands.append({'type': 'cycle', 'commands': self.cycle_commands})
                self.cycle_commands = []
            else:
                cmd = self._parse_command(line)
                if cmd:
                    if self.in_cycle:
                        self.cycle_commands.append(cmd)
                    else:
                        commands.append(cmd)
        
        return commands

    def _parse_command(self, line: str) -> Optional[Dict]:
        """Парсит одну команду"""
        patterns = {
            'click': r'click\((.+\.png)\)',
            'check': r'check\((.+\.png)\)',
            'wait': r'wait\((\d+)\)',
            'custom': r'(\w+)\(([^)]*)\)'
        }
        
        for cmd_type, pattern in patterns.items():
            match = re.fullmatch(pattern, line, re.IGNORECASE)
            if match:
                if cmd_type in ['click', 'check']:
                    return {'type': cmd_type, 'image': match.group(1)}
                elif cmd_type == 'wait':
                    return {'type': cmd_type, 'seconds': int(match.group(1))}
                else:
                    return {'type': 'custom', 'name': match.group(1), 'args': match.group(2)}
        
        return None

    async def _random_delay(self, in_cycle: bool = False):
        """Случайная задержка"""
        if in_cycle:
            delay = random.uniform(self.cycle_min_delay, self.cycle_max_delay)
        else:
            delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)

    async def execute_click(self, image_path: str) -> bool:
        """Выполняет клик по изображению"""
        if not self.click_func:
            raise ValueError("Click function not provided")
        
        print(f"Кликаем по {image_path}")
        location = self.locate_func(image_path) if self.locate_func else None
        print(location)
        
        if location:
            x, y = location[0], location[1]
            result = self.click_func(x, y)
            return result
        await self._trigger_hook('no_image', image_path)
        print(f"Изображение {image_path} не найдено")
        return False

    async def execute_check(self, image_path: str) -> bool:
        """Проверяет наличие изображения на экране"""
        if not self.locate_func:
            raise ValueError("Locate function not provided")
        
        print(f"Проверяем {image_path}")
        location = self.locate_func(image_path)
        return location is not None

    async def execute_commands(self, commands: List[Dict]):
        """Выполняет список команд"""
        self._is_running = True
        self._stop_requested = False
        
        try:
            for cmd in commands:
                if self._stop_requested:
                    print("Выполнение прервано")
                    break
                
                if cmd['type'] == 'click':
                    await self.execute_click(cmd['image'])
                    await self._random_delay(self.in_cycle)
                elif cmd['type'] == 'check':
                    if not await self.execute_check(cmd['image']):
                        print(f"Проверка не пройдена: {cmd['image']}")
                        break
                    await self._random_delay(self.in_cycle)
                elif cmd['type'] == 'wait':
                    await asyncio.sleep(cmd['seconds'])
                elif cmd['type'] == 'cycle':
                    await self.execute_cycle(cmd['commands'])
                elif cmd['type'] == 'custom':
                    await self.execute_custom(cmd['name'], cmd['args'])
        finally:
            self._is_running = False

    async def execute_cycle(self, commands: List[Dict], max_attempts: int = 3):
        """Выполняет цикл команд"""
        attempt = 0
        while attempt < max_attempts and not self._stop_requested:
            print(f"Цикл, попытка {attempt + 1}/{max_attempts}")
            success = True
            
            for cmd in commands:
                if self._stop_requested:
                    break
                
                if cmd['type'] == 'click':
                    if not await self.execute_click(cmd['image']):
                        success = False
                        break
                    await self._random_delay(True)
                elif cmd['type'] == 'check':
                    if not await self.execute_check(cmd['image']):
                        success = False
                        break
                    await self._random_delay(True)
                elif cmd['type'] == 'wait':
                    await asyncio.sleep(cmd['seconds'])
                elif cmd['type'] == 'custom':
                    if not await self.execute_custom(cmd['name'], cmd['args']):
                        success = False
                        break
            
            if success:
                print("Цикл выполнен успешно")
                await self._trigger_hook('success', attempt)
                attempt = 0
            else:
                attempt += 1
                if attempt < max_attempts and not self._stop_requested:
                    print("Повторяем цикл...")
                    await asyncio.sleep(random.uniform(2, 3))
        
        print("Цикл не выполнен после максимального количества попыток")
        return False

    async def execute_custom(self, name: str, args: str):
        """Выполняет пользовательскую команду (может быть переопределен)"""
        print(f"Custom command: {name}({args})")
        return True

    async def run_script(self, script: str):
        """Запускает выполнение скрипта"""
        if self._is_running:
            await self._queue.put(script)
            return
        
        self._current_script = script
        commands = self.parse_commands(script)
        await self.execute_commands(commands)
        
        # Обработка очереди
        while not self._queue.empty():
            next_script = await self._queue.get()
            commands = self.parse_commands(next_script)
            await self.execute_commands(commands)

    async def stop(self):
        """Останавливает выполнение"""
        self._stop_requested = True
        while self._is_running:
            await asyncio.sleep(0.1)

    async def add_script(self, script: str):
        """Добавляет скрипт в очередь выполнения"""
        await self._queue.put(script)
        if not self._is_running:
            await self.run_script(await self._queue.get())

    def is_running(self) -> bool:
        """Проверяет, выполняется ли скрипт"""
        return self._is_running
