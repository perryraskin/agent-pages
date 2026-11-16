// Compose only real browser captures produced by tests/working.mjs --capture.
import fs from 'node:fs';import path from 'node:path';import zlib from 'node:zlib';import puppeteer from 'puppeteer-core';
const out='apps/web/build/working/captures';
const screens=['working','reveal','done'].map(n=>fs.readFileSync(`${out}/${n}-390.png`).toString('base64'));
const browser=await puppeteer.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:process.env.CI&&process.platform==='linux'?['--no-sandbox']:[]});
try{const p=await browser.newPage();
await p.setViewport({width:2700,height:2020,deviceScaleFactor:1,isMobile:false});
await p.setContent(`<style>*{box-sizing:border-box}body{margin:0;background:#eeeae4;color:#302a28;font-family:-apple-system,BlinkMacSystemFont,sans-serif}.top{position:absolute;left:155px;top:96px}.eyebrow{font-size:28px;letter-spacing:5px;color:#52796c;font-weight:600}.title{font-size:82px;letter-spacing:-3px;margin-top:20px;font-weight:500}.note{position:absolute;right:155px;top:125px;font-size:28px;color:#776d65;line-height:1.6;text-align:right}.grid{position:absolute;top:345px;left:170px;right:170px;display:flex;justify-content:space-between}.item{width:680px;text-align:center}.caption{font-size:42px;font-weight:500;letter-spacing:-1px;margin-bottom:38px}.frame{padding:12px;background:#373430;border-radius:62px;box-shadow:0 20px 40px #49383218}.screen{overflow:hidden;border-radius:50px;background:#f4f1ee}.screen img{display:block;width:100%}</style><div class="top"><div class="eyebrow">AGENT PAGES</div><div class="title">Watch a Page take shape.</div></div><div class="note">One Page, three moments.<br>Real web renders · Synthetic examples</div><div class="grid">${screens.map((s,i)=>`<div class="item"><div class="caption">${['01 · Work begins','02 · New details arrive','03 · Ready to enjoy'][i]}</div><div class="frame"><div class="screen"><img src="data:image/png;base64,${s}"></div></div></div>`).join('')}</div>`);
await p.evaluate(()=>Promise.all([...document.images].map(i=>i.decode())));
await p.screenshot({path:'docs/images/working-states.png'});
// Retain only essential PNG chunks; recompress the lossless raster at level 9.
const raw=fs.readFileSync('docs/images/working-states.png'), chunks=[], data=[];let pos=8;
while(pos<raw.length){const n=raw.readUInt32BE(pos),type=raw.toString('ascii',pos+4,pos+8),chunk=raw.subarray(pos,pos+n+12);if(type==='IDAT')data.push(raw.subarray(pos+8,pos+8+n));else if(['IHDR','PLTE','tRNS','IEND'].includes(type))chunks.push({type,chunk});pos+=n+12;}
function crc(b){let c=0xffffffff;for(const v of b){c^=v;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;}
const compressed=zlib.deflateSync(zlib.inflateSync(Buffer.concat(data)),{level:9}), idat=Buffer.alloc(compressed.length+12);idat.writeUInt32BE(compressed.length);idat.write('IDAT',4);compressed.copy(idat,8);idat.writeUInt32BE(crc(idat.subarray(4,-4)),idat.length-4);
const final=Buffer.concat([raw.subarray(0,8),...chunks.filter(c=>c.type!=='IEND').map(c=>c.chunk),idat,chunks.find(c=>c.type==='IEND').chunk]);fs.writeFileSync('docs/images/working-states.png',final);if(final.length>=1500000)throw Error('PNG exceeds budget');
for(const width of [880,390]){await p.setViewport({width,height:Math.ceil(width*2020/2700),deviceScaleFactor:1});await p.setContent(`<style>body{margin:0}img{display:block;width:100%}</style><img src="data:image/png;base64,${final.toString('base64')}">`);await p.evaluate(()=>document.images[0].decode());await p.screenshot({path:path.join(out,`review-${width}.png`)});}
console.log('Composed working-state gallery.');
}finally{await browser.close();}
