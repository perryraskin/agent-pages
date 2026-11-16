import {build} from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const root=process.cwd(),out='apps/web/build/working';
fs.mkdirSync(out,{recursive:true});
const common={bundle:true,write:false,jsx:'automatic',alias:{'grok/canvas':path.resolve('packages/renderer/canvas.tsx')},define:{'process.env.NODE_ENV':'"production"'}};
for(const revised of [false,true]){
 const source=`import Page from './examples/working/page.tsx';`;
 const ssr=await build({...common,platform:'node',format:'cjs',stdin:{resolveDir:root,loader:'tsx',contents:`import {renderToString} from 'react-dom/server';${source}export const html=renderToString(<Page revised={${revised}}/>);`}});
 const temp=path.resolve(out,`render-${revised}.cjs`);fs.writeFileSync(temp,ssr.outputFiles[0].text);
 const {html}=createRequire(import.meta.url)(temp);fs.unlinkSync(temp);
 const client=await build({...common,platform:'browser',format:'iife',minify:true,stdin:{resolveDir:root,loader:'tsx',contents:`import {hydrateRoot} from 'react-dom/client';${source}hydrateRoot(document.getElementById('root'),<Page revised={${revised}}/>);`}});
 fs.writeFileSync(`${out}/${revised?'after':'before'}.html`,`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Weekend studio</title><style>${fs.readFileSync('packages/renderer/canvas.css','utf8')}</style></head><body><!--WORK--><div id="root">${html}</div><script>${client.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')}</script></body></html>`);
}
