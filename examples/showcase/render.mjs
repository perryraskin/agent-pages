// Run from repository root: node examples/showcase/render.mjs
import {build} from 'esbuild';
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import zlib from 'node:zlib';
const root=process.cwd(), out=path.join(root,'apps/web/build/showcase');
fs.mkdirSync(out,{recursive:true});
const common={bundle:true,write:false,jsx:'automatic',alias:{'grok/canvas':path.join(root,'packages/renderer/canvas.tsx')},define:{'process.env.NODE_ENV':'"production"'}};
const browser=await puppeteer.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:process.env.CI?['--no-sandbox']:[]});
try {
const p=await browser.newPage();await p.setViewport({width:390,height:844,deviceScaleFactor:3,isMobile:true,hasTouch:true});await p.emulateMediaFeatures([{name:'prefers-color-scheme',value:'light'}]);
const screens=[];
for(const name of ['plan','decision','form']){
 const entry=path.join(root,`examples/showcase/${name}.tsx`);
 const ssr=await build({...common,platform:'node',format:'cjs',stdin:{resolveDir:root,loader:'tsx',contents:`import {renderToString} from 'react-dom/server';import Page from ${JSON.stringify(entry)};export const html=renderToString(<Page/>);`}});
 const tmp=path.join(out,`${name}.cjs`);fs.writeFileSync(tmp,ssr.outputFiles[0].text);const {html}=createRequire(import.meta.url)(tmp);fs.unlinkSync(tmp);
 const client=await build({...common,platform:'browser',format:'iife',minify:true,stdin:{resolveDir:root,loader:'tsx',contents:`import {hydrateRoot} from 'react-dom/client';import Page from ${JSON.stringify(entry)};hydrateRoot(document.getElementById('root'),<Page/>);`}});
 await p.setContent(`<meta name="viewport" content="width=device-width, initial-scale=1"><style>${fs.readFileSync('packages/renderer/canvas.css','utf8')}</style><div id="root">${html}</div><script>${client.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')}</script>`);
 await p.evaluate(()=>document.fonts.ready);
 if(name==='form'){await p.click('button');await p.waitForFunction(()=>document.body.innerText.includes('You’re on the list'));await p.select('select','Ink drawing');await p.click('button');await p.waitForFunction(()=>document.body.innerText.includes('Ink drawing is selected'));await p.select('select','Paper collage');await p.click('button');}
 const text=await p.evaluate(()=>document.body.innerText);if(/https?:|localhost|\/Users\/|@|perry|token/i.test(text))throw Error('Unexpected identifying text');
 if(await p.evaluate(()=>document.documentElement.scrollWidth>390))throw Error('Horizontal overflow');
 fs.writeFileSync(path.join(out,`${name}.txt`),text);
 await p.screenshot({path:path.join(out,`${name}.png`)});screens.push(fs.readFileSync(path.join(out,`${name}.png`)).toString('base64'));
}
await p.setViewport({width:2700,height:2020,deviceScaleFactor:1,isMobile:false});
await p.setContent(`<style>*{box-sizing:border-box}body{margin:0;background:#eeeae4;color:#302a28;font-family:-apple-system,BlinkMacSystemFont,sans-serif}.top{position:absolute;left:155px;top:96px}.eyebrow{font-size:28px;letter-spacing:5px;color:#52796c;font-weight:600}.title{font-size:82px;letter-spacing:-3px;margin-top:20px;font-weight:500}.note{position:absolute;right:155px;top:125px;font-size:28px;color:#776d65;line-height:1.6;text-align:right}.grid{position:absolute;top:345px;left:170px;right:170px;display:flex;justify-content:space-between}.item{width:680px;text-align:center}.caption{font-size:42px;font-weight:500;letter-spacing:-1px;margin-bottom:38px}.frame{padding:12px;background:#373430;border-radius:62px;box-shadow:0 20px 40px #49383218}.screen{overflow:hidden;border-radius:50px;background:#f4f1ee}.screen img{display:block;width:100%}</style><div class="top"><div class="eyebrow">AGENT PAGES</div><div class="title">From idea to action.</div></div><div class="note">Pages made for you.<br>Real web renders · Synthetic examples</div><div class="grid">${screens.map((s,i)=>`<div class="item"><div class="caption">${['Make a plan','Choose with clarity','Take the next step'][i]}</div><div class="frame"><div class="screen"><img src="data:image/png;base64,${s}"></div></div></div>`).join('')}</div>`);
await p.evaluate(()=>Promise.all([...document.images].map(i=>i.decode())));
await p.screenshot({path:'docs/images/showcase.png'});
// Retain only essential PNG chunks; recompress the lossless raster at level 9.
const raw=fs.readFileSync('docs/images/showcase.png'), chunks=[], data=[];let pos=8;
while(pos<raw.length){const n=raw.readUInt32BE(pos),type=raw.toString('ascii',pos+4,pos+8),chunk=raw.subarray(pos,pos+n+12);if(type==='IDAT')data.push(raw.subarray(pos+8,pos+8+n));else if(['IHDR','PLTE','tRNS','IEND'].includes(type))chunks.push({type,chunk});pos+=n+12;}
function crc(b){let c=0xffffffff;for(const v of b){c^=v;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;}
const compressed=zlib.deflateSync(zlib.inflateSync(Buffer.concat(data)),{level:9}), idat=Buffer.alloc(compressed.length+12);idat.writeUInt32BE(compressed.length);idat.write('IDAT',4);compressed.copy(idat,8);idat.writeUInt32BE(crc(idat.subarray(4,-4)),idat.length-4);
const final=Buffer.concat([raw.subarray(0,8),...chunks.filter(c=>c.type!=='IEND').map(c=>c.chunk),idat,chunks.find(c=>c.type==='IEND').chunk]);fs.writeFileSync('docs/images/showcase.png',final);if(final.length>=1500000)throw Error('PNG exceeds budget');
for(const width of [880,390]){await p.setViewport({width,height:Math.ceil(width*2020/2700),deviceScaleFactor:1});await p.setContent(`<style>body{margin:0}img{display:block;width:100%}</style><img src="data:image/png;base64,${final.toString('base64')}">`);await p.evaluate(()=>document.images[0].decode());await p.screenshot({path:path.join(out,`review-${width}.png`)});}
console.log(`Rendered three 390×844 @3x screens; composite 2700×2020, ${final.length} bytes. Form interaction passed.`);
}finally{await browser.close();}
