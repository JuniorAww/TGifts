import { Telegraf, Input } from 'telegraf'
import { readdir, stat, unlink } from 'node:fs/promises'
//import ffmpeg from 'fluent-ffmpeg'
import path from 'node:path'

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN
const ADMIN = process.env.ADMIN.split(',')

export default class TelegramBot {
    constructor({ workers, save }, meta) {
        this.bot = null;
        this.workers = workers
        this.save = save
        this.meta = meta
        
        this.setup = false
    }
    
    launch() {
        if(!this.setup) {
            this.setup = true;
            this.bot = new Telegraf(TELEGRAM_TOKEN)
            this.bot.on('message', ctx => this.handleMessage(this, ctx))
            process.once('SIGINT', () => this.bot.stop('SIGINT'))
            process.once('SIGTERM', () => this.bot.stop('SIGTERM'))
        }
        
        this.bot.launch()
        console.log("Бот запущен!")
    }
    
    async handleMessage(bot, ctx) {
        console.log(ctx.from)
        
        const { id } = ctx.from
        
        if(!ADMIN.some(x => x === id + "")) return;
        
        const text = ctx.message.text || ctx.message.caption
        
        try {
            if(text.match('/fetch ')) return bot.fetchWorker(ctx, text)
            else if(text.match('/add ')) return bot.addWorker(ctx, text)
            else if(text.match('/click ')) return bot.sendClickRequest(ctx, text)
            else if(text.match('/start')) return bot.handleStart(ctx)
            else if(text.match('/save ')) return bot.saveImage(ctx)
            else if(text.match('/click_img ')) return bot.clickOnSavedImage(ctx)
            //else if(text.match('/seq ')) return bot.setSequence(ctx)
        } catch (e) {
            // notifyAdmins
            console.log(e)
        }
    }

    async sequenceUpdated(data) {
        console.log(data)
        if(data.result === "success") return;
        this.notifyAdmins(JSON.stringify(data))
    }
    
    notifyAdmins(text) {
        ADMIN.forEach(async x => {
            await this.bot.telegram.sendMessage(x, text)
        })
    }
    
    async handleStart(ctx) {
        const name = ctx.from.first_name.length ? ctx.from.first_name : ctx.from.username
        await ctx.reply(`🦊 Приветствую<b>${name ? ', ' + name : ''}</b>!`
        + `\n<b>Хочешь заняться закупкой подарков профессионально?\nПрисоединяйся!</b>`
        + `\n\n⭐ Запущено воркеров: <b>${this.workers.filter(x => x.active).length}/${this.workers.length}</b>`
        + `\n🧭 Магазин подарков проверен: <b>`
        + `${((Date.now() - this.meta.shopLastCheck) / 100).toFixed() / 10} сек. назад</b>`,
        { parse_mode: 'HTML' })
    }
    
    async setSequence(ctx) {
        const args = ctx.message.text.split('\n')
        const worker = this.workers.find(x => x.name === name)
        if(!worker) return await ctx.reply(`🦊 Увы, такого нет!`)
        
        if(!worker.ws.send) return await ctx.reply(`Не подключен!`)

        // click(avatar.png)
        // cycle start
        // click(user_menu.png)
        // click(user_gift_menu.png)
        // click(rare_gifts.png)
        // check(previous_gifts_look.png)
        // cycle end
        
        worker.ws.send(`{"action":"set_sequence","sequence":${args}}`)
    }
    
    async saveImage(ctx) {
        if(!ctx.message.caption) return await ctx.reply(`caption is undefined`)
        const [ cmd, name, filename ] = ctx.message.caption.split(' ')
        const worker = this.workers.find(x => x.name === name)
        if(!worker) return await ctx.reply(`🦊 Увы, такого нет!`)
        
        if(!worker.ws.send) return await ctx.reply(`Не подключен!`)

        const fileLink = await ctx.telegram.getFileLink(ctx.message.photo[0].file_id);
        
        const response = await fetch(fileLink, { responseType: 'arraybuffer' });
        
        const base64Image = Buffer.from(await response.arrayBuffer(), 'binary').toString('base64');
        
        worker.ws.send(`{"action":"save","buffer":"${base64Image}","name":"${filename}"}`)
    }
    
    async clickOnSavedImage(ctx) {
        const [ cmd, name, filename ] = ctx.message.text.split(' ')
        const worker = this.workers.find(x => x.name === name)
        if(!worker) return await ctx.reply(`🦊 Увы, такого нет!`)
        
        if(!worker.ws.send) return await ctx.reply(`Не подключен!`)
        worker.ws.send(`{"action":"click_image","name":"${filename}"}`)
        setTimeout(() => {
            this.fetchWorker(ctx, name)
        }, 2500)
    }
    
    /*async getLiveUpdates(ctx) {
        const { id } = ctx.from
        const name = ctx.message.text.split(' ')[1]
        if(!this.workers.find(x => x.name === name)) return ctx.reply(`🦊 Такого воркера нет!`)
        
        const existing = this.liveUpdates.find(x => x.userId === id)
        if(existing) this.liveUpdates.splice(this.liveUpdates.indexOf(existing), 1)
        
        const { message_id } = await ctx.replyWithPhoto({ source: "fox.png" }, { caption: `🦊 Отслеживание` })
        this.liveUpdates.push({ userId: id, worker: name, messageId: message_id })
    }*/

    async sendClickRequest(ctx, text) {
        const [ cmd, name, x, y ] = ctx.message.text.split(' ')
        const worker = this.workers.find(x => x.name === name)
        if(!worker) return await ctx.reply(`🦊 Увы, такого нет!`)
        
        if(!worker.ws.send) return await ctx.reply(`Не подключен!`)
        worker.ws.send(`{"action":"click","x":${x},"y":${y}}`)
        setTimeout(() => {
            this.fetchWorker(ctx, name)
        }, 2500)
    }
    
    async addWorker(ctx) {
        const [ cmd, name ] = ctx.message.text.split(' ')
        
        if(this.workers.find(x => x.name === name)) return ctx.reply(`🦊 Имя занято!`)
        
        this.workers.push({
            name,
            active: false,
            enabled: true,
            ping: 0,
            balance: 0,
            stats: {
                shopChecks: 0,
                giftsBought: 0,
            },
            logs: [],
        })
        this.save()
        await ctx.reply(`🦊 Ожидаем подключение...`)
        const worker = this.workers.find(x => x.name === name)
        
        for(let x = 20; x > 0; x--) {
            if(worker.active) break;
            await new Promise(r => setTimeout(r, 1000))
        }
        
        if(!worker.active) {
            if(worker.logs.length) await ctx.reply(`🦊 Не удалось подключиться :(`
                                    + `\n${worker.logs.join('\n')}`)
            else await ctx.reply(`🦊 К сожалению, никто не подключился :(`)
        }
        else await ctx.reply(`🦊 Успешное подключение!\n${worker.logs.join("\n")}`)
        
        this.save()
    }
    
    async fetchWorker(ctx, text) {
        const name = text.slice(text.indexOf(' ') + 1)
        const worker = this.workers.find(x => x.name === name)
        if(!worker) return await ctx.reply(`🦊 Увы, такого нет!`)
        
        const path = "./screenshots/" + name + '.png'
        const { mtime } = await stat(path)
        
        await ctx.replyWithPhoto({ source: path },
        { caption: `🦊 ID: ${name}\nPing: ${secAgo(worker.ping)}\n\nСнимок экрана (${secAgo(mtime)})` })
        
        /*const updates = this.liveUpdates.filter(x => x.worker === name)
        if(!updates.length) return;
        
        const files = await getSortedFiles('./screenshots', name + '_') 
        
        if(files.length === 25) {
            if(updates.length) {
                const spath = "screenshots/" + name
                const gif = `${spath}.mp4`
                ffmpeg()
                    .input(`${spath}_%d.png`)
                    .inputFPS(1)
                    .save(gif)
                    .on('end', async() => {
                        for(let i = 1; i <= 20; i++) unlink(`${spath}_${i}.png`);
                        const photoSource = { source: gif }
                        
                        const text = `🦊 Обновлено`
                        
                        const message = 
                                await this.bot.telegram.sendVideo(ADMIN[0], photoSource)
                        await this.bot.telegram.deleteMessage(ADMIN[0], message.message_id)
                        console.log(message)
                        
                        const fileId = message.video.file_id
                        
                        for(const { userId, messageId } of updates.splice(0, 1)) {
                            console.log('Editing photo for ' + userId)
                            await this.bot.telegram.editMessageMedia(userId, messageId, null, {
                                type: 'video',
                                media: fileId,
                                caption: 'test'
                            })
                        }
                    })
                    .on('error', (err) => console.log("Ошибка!", err))
            }
        }*/
    }
}

const secAgo = unix => {
    return `${((Date.now() - unix) / 100).toFixed() / 10} сек. назад`
}

async function getSortedFiles(dir, pattern) {
    const files = await readdir(dir);
    const filteredFiles = files.filter(file => file.includes(pattern));

    const filesWithStats = await Promise.all(
        filteredFiles.map(async (file) => {
            const filePath = path.join(dir, file);
            const stats = await stat(filePath);
            return {
                name: file,
                path: filePath,
                mtime: stats.mtime,
            };
        })
    );

    return filesWithStats.sort((a, b) => a.mtime.getTime() - b.mtime.getTime());
}

process.on('uncaughtException', (err) => {
  console.error('Uncaught Exception:', err);
  // Здесь можно перезапустить приложение или сделать другие действия
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  // Обработаем ошибку или перезапустим
});



