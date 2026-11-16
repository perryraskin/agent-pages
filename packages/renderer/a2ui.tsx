// Deliberately small A2UI 1.0 component catalog for self-contained Hermes Pages.
// No iframe, remote renderer, model call, or implicit agent action.
import React, {useState} from 'react';
export type A2UINode = {id:string; component:string; [key:string]:any};
const TYPES = new Set(['Column','Row','Text','Heading','Card','Badge','TextField','CheckBox','Button','Divider']);
export function validateA2UI(components:A2UINode[]) {
  if (!Array.isArray(components) || components.length > 200) throw Error('A2UI requires at most 200 components');
  const nodes = new Map<string,A2UINode>();
  for(const n of components){
    if(!n || typeof n.id !== 'string' || nodes.has(n.id)) throw Error('Invalid or duplicate A2UI id');
    if(!TYPES.has(n.component)) throw Error('Unsupported Hermes A2UI component: '+n.component);
    nodes.set(n.id,n);
  }
  if(!nodes.has('root')) throw Error('A2UI root is required');
  const visit=(id:string,parents:Set<string>)=>{
    const n=nodes.get(id); if(!n) throw Error('Missing A2UI component: '+id);
    if(parents.has(id)) throw Error('Cyclic A2UI reference');
    const children=n.children ?? (n.child ? [n.child] : []);
    if(!Array.isArray(children)) throw Error('A2UI children must be an array');
    for(const child of children) visit(child,new Set([...parents,id]));
  };
  for(const id of nodes.keys()) visit(id,new Set()); return nodes;
}
export function A2UISurface({components,dataModel={},onAction}:{components:A2UINode[];dataModel?:Record<string,any>;onAction?:(name:string,context:Record<string,any>)=>void}){
  const nodes=validateA2UI(components);
  const [data,setData]=useState(dataModel);
  const [notice,setNotice]=useState('');
  const resolve=(v:any):any=>{
    if(v && typeof v==='object' && typeof v['@path']==='string') return v['@path'].split('/').filter(Boolean).reduce((o:any,k:string)=>o?.[k],data) ?? '';
    return v;
  };
  const set=(binding:any,value:any)=>{
    const keys=binding?.['@path']?.split('/').filter(Boolean);
    if(!keys?.length || keys.some((k:string)=>['__proto__','constructor','prototype'].includes(k))) return;
    setData(old=>{const next=JSON.parse(JSON.stringify(old));let at=next;for(const k of keys.slice(0,-1)) at=at[k] ??= {};at[keys[keys.length-1]]=value;return next;});
  };
  const render=(id:string):React.ReactNode=>{
    const n=nodes.get(id)!; const children=()=> (n.children ?? (n.child?[n.child]:[])).map(render);
    const text=()=>String(resolve(n.text ?? n.label ?? ''));
    switch(n.component){
      case 'Column':return <div key={id} style={{display:'grid',gap:16}}>{children()}</div>;
      case 'Row':return <div key={id} style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'center'}}>{children()}</div>;
      case 'Card':return <section key={id} style={{border:'1px solid currentColor',borderRadius:12,padding:16}}>{children()}</section>;
      case 'Heading':return <h2 key={id}>{text()}</h2>;
      case 'Text':return <p key={id}>{text()}</p>;
      case 'Badge':return <span key={id} style={{border:'1px solid currentColor',borderRadius:20,padding:'3px 10px'}}>{text()}</span>;
      case 'Divider':return <hr key={id}/>;
      case 'TextField':return <label key={id} style={{display:'grid',gap:8}}>{n.label}<input value={String(resolve(n.value))} onChange={e=>set(n.value,e.target.value)} style={{font:'inherit',padding:10,border:'1px solid',borderRadius:8}}/></label>;
      case 'CheckBox':return <label key={id}><input type='checkbox' checked={Boolean(resolve(n.value))} onChange={e=>set(n.value,e.target.checked)}/>{n.label}</label>;
      case 'Button':return <button key={id} type='button' style={{font:'inherit',padding:'10px 16px',cursor:'pointer'}} onClick={()=>{
        const event=n.onClick?.event;if(!event){setNotice('No action configured.');return;}
        const context=Object.fromEntries(Object.entries(event.context ?? {}).map(([k,v])=>[k,resolve(v)]));
        if(onAction) onAction(event.name,context);else setNotice('This Page has no agent action connection.');
      }}>{n.child ? render(n.child) : text()}</button>;
    }
  };
  return <div data-hermes-a2ui>{render('root')}<p role='status' aria-live='polite'>{notice}</p></div>;
}
