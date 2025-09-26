import 'dotenv/config'
import WS from 'ws'
import fs from 'fs'
import Bot from "./jsniff"
import https from 'https';

const {
	workers,
    users,
    meta
} = JSON.parse(fs.readFileSync('./data.json', 'UTF-8'))

const save = () => fs.writeFileSync('./data.json', JSON.stringify({ users, workers, meta }, null, 2))
// TODO sqlite3?

workers.forEach(x => {
    x.active = false
    x.enabled = false
})

const bot = new Bot({ workers, save }, meta)
bot.launch()

const server = https.createServer({
    cert: fs.readFileSync('https/server.crt'),
    key: fs.readFileSync('https/server.key'),
    ca: fs.readFileSync('https/ca.crt'),
    requestCert: true,
    rejectUnauthorized: true
})

const wss = new WS.WebSocketServer({ server })
server.listen(3033)

let nextId = 1
wss.on('connection', function connection(ws) {
	let worker = null
    let connected = false
	
    const prefix = `[${nextId}] `
    nextId++ 
    
	console.log(prefix + 'Connecting new client... [suda aipi]')
	
    const reject = reason => {
        console.log(prefix + 'Rejecting with reason:', reason)
        ws.send('{"status":"rejected","info":"' + reason + '"}')
        return ws.close()
    }
    
	ws.on('error', console.error)
	
	ws.on('message', data => {
        const str = data.toString()
		console.log(prefix + str.slice(0, 60) + (str.length > 60 ? "..." : ""))
		
		let input
		try {
			input = JSON.parse(data)
		} catch (e) { console.log(e); console.log(data); return }
		
		const { status, action } = input
		
        if(status === 'ready') {
            const { name } = input
            
            worker = workers.find(x => x.name === name)
            
            if(!worker) return reject('worker name is unknown')
            else if(worker.active) return reject('already active, wait 5 seconds')
            
            worker.ws = ws
            worker.active = true
            worker.ping = Date.now()
            
            if(!worker.enabled) enableWorker(worker)
            ws.send('{"status":"approved"}')
        }
        
        if(!worker) {
            ws.close()
            return;
        }
        
		if(action === "sync") return sync(ws, input)
		if(action === "screenshot") {
            const { data, timestamp } = input
            worker.ping = Date.now()
            //const photo_id = Math.ceil(Date.now() % 10000 / 1000)
            fs.writeFileSync(`./screenshots/${worker.name}.png`, Buffer.from(data, 'base64'));
            return;
        }
        if(action === "seq_status") {
            const { data } = input
            console.log(data)
            if(data.result === "success") meta.shopLastCheck = Date.now()
            else {
                fs.copyFile(`./screenshots/${worker.name}.png`, `./screenshots/${worker.name}-${Date.now()}.png`, (err => {
                    console.log('Ошибка записи', e)
                    bot.sequenceUpdated(`Ошибка сохранения скриншота`)
                }))
                fs.access(`./screenshots/${worker.name}.png`, fs.constants.F_OK, (err) => {
                    if (err) return bot.sequenceUpdated('Не удалось сохранить скриншот ошибки!');
                    fs.copyFile(`./screenshots/${worker.name}.png`, `./screenshots/${worker.name}-${Date.now()}.png`, 
                    (err => {
                        if(!err) return;
                        console.log('Ошибка записи', e)
                        bot.sequenceUpdated(`Ошибка сохранения скриншота`)
                    }))
                });
            }
            bot.sequenceUpdated(data)
        }
	})
	
	ws.on('end', () => {
		connected = false;
        if(worker) worker.connected = false
	})
})

const enableWorker = async(worker, ws) => {
    let silentTimings = 0
    
    worker.enabled = true     
    while(worker.enabled) {
        const now = Date.now()
        if(now - worker.ping > 1000) silentTimings += 1
        else {
            if(silentTimings >= 5) {
                worker.active = true
                bot.notifyAdmins("worker " + worker.name + "is alive!")
            }
            silentTimings = 0
        }
        
        if(silentTimings === 5) {
            worker.active = false
            bot.notifyAdmins("worker " + worker.name + " stopped working")
        }
        
        await new Promise(r => setTimeout(r, 1000));
    }
}








// Каждый воркер проверяется
// центральный бот отсылает запросы на проверки подарков, воркеры выполняют и отправляют запрос

// Подключение воркеров к WSS
// инициализация -> добавление в лист -> каждые 5 секунд проверка работоспособности
// если аккаунт не отвечает, уведомление админа
// проверка подарков должна происходить каждые 20 секунд
// значит, каждый аккаунт проверяет подарки раз в 60 секунд, между собой интервал

// Также должен быть третий скрипт, который проверяет работоспособность WSS
// и аналогично если не работает - присылает уведомление через 2 бота
