import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import http from 'node:http';
import puppeteer from 'puppeteer-core';
const root=path.resolve('apps/web/build/working/build');
const advance=stage=>execFileSync('python3',['examples/working/fixture.py',stage]);
execFileSync(process.execPath,['examples/working/build.mjs']);
const server=http.createServer((req,res)=>{
 const name=new URL(req.url,'http://localhost').pathname;
 if(!/^\/(studio\.html|live\/studio\.(json|prev\.html))$/.test(name)){res.writeHead(404).end();return;}
 try{res.setHeader('Content-Type',name.endsWith('.json')?'application/json':'text/html');res.setHeader('Cache-Control','no-store');res.end(fs.readFileSync(root+name));}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await puppeteer.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:process.env.CI&&process.platform==='linux'?['--no-sandbox']:[]});
const captures=process.argv.includes('--capture');
const out='apps/web/build/working/captures';fs.mkdirSync(out,{recursive:true});
try{
 for(const [width,height,reduce] of [[390,844,false],[1440,1000,false],[390,844,true]]){
  advance('start');const p=await browser.newPage(), errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.setRequestInterception(true);
  p.on('request',r=>{if(!r.url().startsWith(origin+'/')){errors.push('External request: '+r.url());r.abort();}else r.continue();});
  await p.setViewport({width,height,deviceScaleFactor:width===390?3:1});
  await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:reduce?'reduce':'no-preference'},{name:'prefers-color-scheme',value:'light'}]);
  await p.goto(origin+'/studio.html');await p.waitForSelector('.hp-work-working');
  await p.waitForFunction(()=>localStorage.getItem('hp-seen:studio'));
  const check=async stage=>{
   const facts=await p.evaluate(()=>({text:document.body.innerText,overflow:document.documentElement.scrollWidth>innerWidth,live:document.querySelector('#hp-work').getAttribute('aria-live')}));
   assert(!facts.overflow,'horizontal overflow');assert.equal(facts.live,'polite');
   assert(!/https?:|localhost|\/Users\/|@|perry|token/i.test(facts.text),'identifying text');
   if(captures&&!reduce){await p.screenshot({path:`${out}/${stage}-${width}.png`});fs.writeFileSync(`${out}/${stage}-${width}.txt`,facts.text);}
  };
  await check('working');
  advance('reveal');
  await p.waitForFunction(()=>document.body.innerText.includes('Eight places') && document.querySelector('.hp-caret.hp-open') && getComputedStyle(document.querySelector('.hp-caret')).display!=='none');
  await p.waitForSelector('.hp-rect');
  await p.waitForFunction(()=>[...document.querySelectorAll('.hp-mark')].every(e=>Number(getComputedStyle(e).opacity)>.95));
  assert.equal(await p.$eval('.hp-flag',e=>e.textContent),'Aster');
  assert(await p.$eval('.hp-caret',e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.height>0;}));
  if(reduce)assert.equal(await p.$eval('.hp-mark',e=>getComputedStyle(e).animationName),'none');
  await check('reveal');
  advance('done');await p.waitForSelector('.hp-work-done');
  assert.equal(await p.$eval('.hp-caret',e=>getComputedStyle(e).display),'none');
  assert(await p.$eval('#root',e=>e.textContent.includes('Eight places')));
  await p.waitForFunction(()=>!document.querySelector('.hp-mark'));
  await check('done');assert.deepEqual(errors,[]);
  // A reload obtains the completed state without a lingering active cursor.
  await p.reload();await p.waitForSelector('.hp-work-done');
  assert.equal(await p.$eval('#hp-work',e=>e.textContent.includes('Done')),true);
  await p.close();
 }
 console.log('PASS working → real content revision + cursor/highlights → done; 390px/1440px; reduced motion; reload; privacy; no overflow or browser errors.');
}finally{await browser.close();await new Promise(r=>server.close(r));}
