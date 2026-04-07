const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys')
const fs = require('fs')
const path = require('path')
const { exec } = require('child_process')
const http = require('http')
const url = require('url')

// ─── Config ───────────────────────────────────────────────────────────────────
const BOT_NAME     = 'Kata-MD'
const BOT_VERSION  = 'v3.0'
const OWNER_NUMBER = process.env.OWNER_NUMBER || '27743266789'
const PREFIX       = process.env.PREFIX || '.'
const PORT         = process.env.PORT || 3000
const DOWNLOAD_DIR = './downloads'

if (!fs.existsSync(DOWNLOAD_DIR)) fs.mkdirSync(DOWNLOAD_DIR)
if (!fs.existsSync('./sessions')) fs.mkdirSync('./sessions')

// ─── State ────────────────────────────────────────────────────────────────────
let prefix      = PREFIX
let botMode     = 'public'
let botPfpUrl   = null
const bannedUsers = new Set()
const activeUsers = {}
const activeSessions = {}  // phone -> sock
let startTime   = Date.now()

// ─── Helpers ──────────────────────────────────────────────────────────────────

function ownerJid() { return OWNER_NUMBER + '@s.whatsapp.net' }
function isOwner(jid) { return jid.replace('@s.whatsapp.net','').replace('@c.us','') === OWNER_NUMBER }
function trackUser(jid, name) {
    if (!activeUsers[jid]) activeUsers[jid] = { name, count: 0 }
    activeUsers[jid].count++
    activeUsers[jid].name = name
}
function runtime() {
    const e = Math.floor((Date.now() - startTime) / 1000)
    return `${Math.floor(e/3600)}h ${Math.floor((e%3600)/60)}m ${e%60}s`
}
function downloadFile(url, filename) {
    return new Promise((resolve, reject) => {
        const fp  = path.join(DOWNLOAD_DIR, filename)
        const cmd = `yt-dlp -f "best[ext=mp4]/best" -o "${fp}" "${url}" --no-playlist --socket-timeout 30`
        exec(cmd, (err, stdout, stderr) => {
            if (err) return reject(stderr || err.message)
            const files = fs.readdirSync(DOWNLOAD_DIR).filter(f => f.startsWith(filename.replace('.mp4','')))
            if (files.length > 0) return resolve(path.join(DOWNLOAD_DIR, files[0]))
            reject('File not found')
        })
    })
}
function downloadAudio(url, filename) {
    return new Promise((resolve, reject) => {
        const fp  = path.join(DOWNLOAD_DIR, filename)
        const cmd = `yt-dlp -f "bestaudio" -o "${fp}" "${url}" --no-playlist --socket-timeout 30`
        exec(cmd, (err, stdout, stderr) => {
            if (err) return reject(stderr || err.message)
            const files = fs.readdirSync(DOWNLOAD_DIR).filter(f => f.startsWith(filename.split('.')[0]))
            if (files.length > 0) return resolve(path.join(DOWNLOAD_DIR, files[0]))
            reject('File not found')
        })
    })
}
function searchYoutube(query) {
    return new Promise((resolve, reject) => {
        exec(`yt-dlp "ytsearch1:${query}" --get-url --get-title --no-playlist -q`, (err, stdout) => {
            if (err) return reject(err.message)
            const lines = stdout.trim().split('\n')
            resolve({ title: lines[0], url: lines[1] })
        })
    })
}

// ─── Web Server (serves website + pairing API) ────────────────────────────────

const server = http.createServer(async (req, res) => {
    const parsed = url.parse(req.url, true)

    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')

    // Serve website
    if (parsed.pathname === '/' || parsed.pathname === '/index.html') {
        const html = fs.readFileSync('./index.html', 'utf8')
        res.writeHead(200, { 'Content-Type': 'text/html' })
        return res.end(html)
    }

    // Health check
    if (parsed.pathname === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        return res.end(JSON.stringify({ status: 'online', bot: BOT_NAME }))
    }

    // Pairing API
    if (parsed.pathname === '/pair') {
        const phone = parsed.query.phone?.replace(/\D/g, '')
        if (!phone || phone.length < 10) {
            res.writeHead(400, { 'Content-Type': 'application/json' })
            return res.end(JSON.stringify({ error: 'Invalid phone number' }))
        }

        console.log(`🔑 Pair request for +${phone}`)

        try {
            const code = await createPairingSession(phone)
            res.writeHead(200, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ code, phone }))
        } catch (e) {
            console.error('Pairing error:', e.message)
            res.writeHead(500, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ error: e.message }))
        }
        return
    }

    res.writeHead(404)
    res.end('Not found')
})

// ─── Pairing Session ──────────────────────────────────────────────────────────

async function createPairingSession(phone) {
    const sessionDir = `./sessions/${phone}`
    if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true })

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir)
    const { version } = await fetchLatestBaileysVersion()

    return new Promise(async (resolve, reject) => {
        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            connectTimeoutMs: 60000,
            keepAliveIntervalMs: 10000,
            browser: ['Kata-MD', 'Chrome', '1.0'],
        })

        sock.ev.on('creds.update', saveCreds)

        let codeResolved = false

        setTimeout(async () => {
            try {
                if (!sock.authState.creds.registered) {
                    const code = await sock.requestPairingCode(phone)
                    console.log(`✅ Code for +${phone}: ${code}`)
                    codeResolved = true
                    activeSessions[phone] = sock
                    resolve(code)

                    // After pairing, attach message handler
                    sock.ev.on('connection.update', async ({ connection }) => {
                        if (connection === 'open') {
                            console.log(`✅ +${phone} connected!`)
                            attachMessageHandler(sock, phone)
                            await sock.sendMessage(ownerJid(), {
                                text: `╔═══════════════════════╗\n  🔥 *${BOT_NAME} ${BOT_VERSION} Online!*\n╚═══════════════════════╝\n\n⚡ Prefix: \`${prefix}\`\n🌐 Mode: PUBLIC\n🌐 Paired via website!\n\nType \`${prefix}menu\` to get started!\n_Stay Dripped_ 💧`
                            })
                        } else if (connection === 'close') {
                            console.log(`Connection closed for +${phone}, reconnecting...`)
                            setTimeout(() => createPairingSession(phone), 5000)
                        }
                    })
                }
            } catch (e) {
                if (!codeResolved) reject(e)
            }
        }, 1500)

        // Timeout
        setTimeout(() => {
            if (!codeResolved) reject(new Error('Timed out generating pair code'))
        }, 30000)
    })
}

// ─── Message Handler ──────────────────────────────────────────────────────────

function attachMessageHandler(sock, phone) {
    sock.ev.on('messages.upsert', async ({ messages }) => {
        const msg    = messages[0]
        if (!msg?.message || msg.key.fromMe) return

        const from   = msg.key.remoteJid
        const sender = msg.key.participant || from
        const name   = msg.pushName || sender.split('@')[0]
        const body   = msg.message?.conversation || msg.message?.extendedTextMessage?.text || ''

        if (!body.startsWith(prefix)) return
        if (bannedUsers.has(sender)) {
            await sock.sendMessage(from, { text: `🚫 You are banned from *${BOT_NAME}*.` })
            return
        }
        if (botMode === 'private' && !isOwner(sender)) {
            await sock.sendMessage(from, { text: `🔒 *${BOT_NAME}* is in *PRIVATE* mode.` })
            return
        }

        trackUser(sender, name)

        const args = body.slice(prefix.length).trim().split(' ')
        const cmd  = args[0].toLowerCase()
        const rest = args.slice(1).join(' ')
        const reply = async (text) => sock.sendMessage(from, { text }, { quoted: msg })

        console.log(`CMD [${from}] ${name}: ${prefix}${cmd}`)

        if (cmd === 'menu') {
            const menuText = `╔━━━━━━━━━━━━━━━━━━━━━━╗\n  🔥 *${BOT_NAME}* ${BOT_VERSION} 🔥\n  _The Dripped Out Bot_\n╚━━━━━━━━━━━━━━━━━━━━━━╝\n\n⚡ *Prefix:* \`${prefix}\`\n🌐 *Mode:* \`${botMode.toUpperCase()}\`\n👑 *Owner:* +${OWNER_NUMBER}\n\n━━━━ 📥 *DOWNLOADER* ━━━━\n${prefix}yt (link) — YouTube video\n${prefix}fb (link) — Facebook video\n${prefix}insta (link) — Instagram reel\n${prefix}song (query) — Download song 🎵\n${prefix}yt-search (query) mp3/mp4\n\n━━━━ 🛠️ *TOOLS* ━━━━\n${prefix}ping — Bot speed ms ⚡\n${prefix}owner — Owner contact 👑\n${prefix}runtime — Bot uptime ⏱️\n\n━━━━ 👥 *GROUP* ━━━━\n${prefix}tagall — Tag everyone 📢\n${prefix}activeusers — Top users 📊\n\n━━━━ 🔐 *OWNER ONLY* ━━━━\n${prefix}public — Open to all\n${prefix}private — Owner only\n${prefix}ban (number) — Ban user 🚫\n${prefix}unban (number) — Unban ✅\n${prefix}setpfp (url) — Set bot pic 🖼️\n${prefix}setprefix (symbol) — New prefix\n\n━━━━━━━━━━━━━━━━━━━━━━━\n🔥 *${BOT_NAME}* | Stay Dripped 💧`
            if (botPfpUrl) {
                await sock.sendMessage(from, { image: { url: botPfpUrl }, caption: menuText }, { quoted: msg })
            } else {
                await reply(menuText)
            }
        } else if (cmd === 'ping') {
            const s = Date.now()
            await reply('🏓 *Pong!*')
            await reply(`⚡ *${BOT_NAME} Speed*\n\n🚀 Response: *${Date.now()-s}ms*\n✅ Status: *Online*\n🔥 *Dripped & Ready*`)
        } else if (cmd === 'runtime') {
            await reply(`⏱️ *${BOT_NAME} Runtime*\n\n🕐 Uptime: *${runtime()}*\n✅ *Running Strong* 💪`)
        } else if (cmd === 'owner') {
            await reply(`👑 *${BOT_NAME} Owner*\n\n📱 +${OWNER_NUMBER}\n💬 wa.me/${OWNER_NUMBER}\n\n_Slide in for support_ 🔥`)
        } else if (cmd === 'yt') {
            if (!rest) return reply(`❌ Send a YouTube link.`)
            await reply('🔴 *YouTube* | Downloading... ⏬')
            try {
                const fid  = Date.now()
                const file = await downloadFile(rest, `${fid}.mp4`)
                const size = fs.statSync(file).size / (1024*1024)
                if (size > 100) { fs.unlinkSync(file); return reply('⚠️ File too large!') }
                await sock.sendMessage(from, { video: fs.readFileSync(file), caption: `🎬 *YouTube Video*\n\n🔥 ${BOT_NAME}` }, { quoted: msg })
                fs.unlinkSync(file)
            } catch (e) { await reply(`❌ Failed: ${String(e).slice(0,100)}`) }
        } else if (cmd === 'fb') {
            if (!rest) return reply(`❌ Send a Facebook link.`)
            await reply('📘 *Facebook* | Downloading... ⏬')
            try {
                const fid  = Date.now()
                const file = await downloadFile(rest, `${fid}.mp4`)
                const size = fs.statSync(file).size / (1024*1024)
                if (size > 100) { fs.unlinkSync(file); return reply('⚠️ File too large!') }
                await sock.sendMessage(from, { video: fs.readFileSync(file), caption: `📘 *Facebook Video*\n\n🔥 ${BOT_NAME}` }, { quoted: msg })
                fs.unlinkSync(file)
            } catch (e) { await reply(`❌ Failed: ${String(e).slice(0,100)}`) }
        } else if (cmd === 'insta') {
            if (!rest) return reply(`❌ Send an Instagram link.`)
            await reply('📸 *Instagram* | Downloading... ⏬')
            try {
                const fid  = Date.now()
                const file = await downloadFile(rest, `${fid}.mp4`)
                const size = fs.statSync(file).size / (1024*1024)
                if (size > 100) { fs.unlinkSync(file); return reply('⚠️ File too large!') }
                await sock.sendMessage(from, { video: fs.readFileSync(file), caption: `📸 *Instagram Reel*\n\n🔥 ${BOT_NAME}` }, { quoted: msg })
                fs.unlinkSync(file)
            } catch (e) { await reply(`❌ Failed: ${String(e).slice(0,100)}`) }
        } else if (cmd === 'song') {
            if (!rest) return reply(`❌ Send a song name.`)
            await reply(`🎵 Searching: *${rest}*...`)
            try {
                const { title, url } = await searchYoutube(rest)
                await reply(`⏬ Downloading: *${title}*...`)
                const fid  = Date.now()
                const file = await downloadAudio(url, `${fid}`)
                if (fs.statSync(file).size/(1024*1024) > 100) { fs.unlinkSync(file); return reply('⚠️ Too large!') }
                await sock.sendMessage(from, { audio: fs.readFileSync(file), mimetype: 'audio/mpeg', ptt: false }, { quoted: msg })
                fs.unlinkSync(file)
            } catch (e) { await reply(`❌ Failed: ${String(e).slice(0,100)}`) }
        } else if (cmd === 'yt-search' || cmd === 'ytsearch') {
            if (!rest) return reply(`❌ Usage: \`${prefix}yt-search <query> mp3/mp4\``)
            const parts = rest.split(' ')
            const fmt   = ['mp3','mp4'].includes(parts[parts.length-1].toLowerCase()) ? parts.pop().toLowerCase() : 'mp4'
            const query = parts.join(' ')
            await reply(`🔍 Searching: *${query}* [${fmt.toUpperCase()}]...`)
            try {
                const { title, url } = await searchYoutube(query)
                await reply(`⏬ Downloading: *${title}*...`)
                const fid = Date.now()
                if (fmt === 'mp3') {
                    const file = await downloadAudio(url, `${fid}`)
                    await sock.sendMessage(from, { audio: fs.readFileSync(file), mimetype: 'audio/mpeg' }, { quoted: msg })
                    fs.unlinkSync(file)
                } else {
                    const file = await downloadFile(url, `${fid}.mp4`)
                    await sock.sendMessage(from, { video: fs.readFileSync(file), caption: `🎬 *${title}*\n\n🔥 ${BOT_NAME}` }, { quoted: msg })
                    fs.unlinkSync(file)
                }
            } catch (e) { await reply(`❌ Failed: ${String(e).slice(0,100)}`) }
        } else if (cmd === 'tagall') {
            if (!from.endsWith('@g.us')) return reply('❌ Groups only!')
            const meta    = await sock.groupMetadata(from)
            const members = meta.participants.map(p => p.id)
            let tags = ''
            members.forEach((m, i) => { tags += `${i+1}. @${m.split('@')[0]}\n` })
            await sock.sendMessage(from, { text: `📢 *Tagging ${members.length} members:*\n\n${tags}\n🔥 ${BOT_NAME}`, mentions: members }, { quoted: msg })
        } else if (cmd === 'activeusers' || cmd === 'active') {
            const sorted = Object.entries(activeUsers).sort((a,b) => b[1].count-a[1].count).slice(0,10)
            if (!sorted.length) return reply('📊 No active users yet.')
            const medals = ['🥇','🥈','🥉','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
            let text = `📊 *Top Users — ${BOT_NAME}*\n\n`
            sorted.forEach(([jid, data], i) => { text += `${medals[i]} ${data.name} — *${data.count}* cmds\n` })
            await reply(text + `\n🔥 ${BOT_NAME}`)
        } else if (cmd === 'ban') {
            if (!isOwner(sender)) return reply('❌ Owner only!')
            if (!rest) return reply(`❌ Usage: \`${prefix}ban 27xxxxxxxxx\``)
            bannedUsers.add(rest.replace('+','').replace(' ','') + '@s.whatsapp.net')
            await reply(`🚫 *Banned!*\n+${rest} banned from ${BOT_NAME}.`)
        } else if (cmd === 'unban') {
            if (!isOwner(sender)) return reply('❌ Owner only!')
            if (!rest) return reply(`❌ Usage: \`${prefix}unban 27xxxxxxxxx\``)
            bannedUsers.delete(rest.replace('+','').replace(' ','') + '@s.whatsapp.net')
            await reply(`✅ *Unbanned!*\n+${rest} can use ${BOT_NAME} again.`)
        } else if (cmd === 'public') {
            if (!isOwner(sender)) return reply('❌ Owner only!')
            botMode = 'public'
            await reply(`🌐 *${BOT_NAME} is now PUBLIC!*`)
        } else if (cmd === 'private') {
            if (!isOwner(sender)) return reply('❌ Owner only!')
            botMode = 'private'
            await reply(`🔒 *${BOT_NAME} is now PRIVATE!*`)
        } else if (cmd === 'setpfp') {
            if (!isOwner(sender)) return reply('❌ Owner only!')
            if (!rest) return reply(`❌ Usage: \`${prefix}setpfp https://image-url.jpg\``)
            botPfpUrl = rest.trim()
            await reply(`🖼️ *Bot pic updated!* 🔥`)
        } else if (cmd === 'setprefix') {
            if (!isOwner(sender)) return reply('❌ Owner only!')
            if (!rest) return reply(`❌ Usage: \`${prefix}setprefix !\``)
            const old = prefix
            prefix = rest.trim()[0]
            await reply(`✅ Prefix: \`${old}\` → \`${prefix}\``)
        } else {
            await reply(`❓ Unknown: \`${prefix}${cmd}\`\nType \`${prefix}menu\` for commands. 🔥`)
        }
    })
}

// ─── Start ────────────────────────────────────────────────────────────────────

server.listen(PORT, () => {
    console.log(`\n╔═══════════════════════════════╗`)
    console.log(`  🔥 ${BOT_NAME} ${BOT_VERSION} Server`)
    console.log(`╚═══════════════════════════════╝`)
    console.log(`🌐 Website: http://localhost:${PORT}`)
    console.log(`🔑 Pair API: http://localhost:${PORT}/pair?phone=27743266789`)
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`)
})
