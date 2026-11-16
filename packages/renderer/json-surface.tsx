import React from 'react';
import {defineCatalog,validateSpec} from '@json-render/core';
import {schema} from '@json-render/react/schema';
import {defineRegistry,Renderer,JSONUIProvider,useBoundProp} from '@json-render/react';
import {z} from 'zod';
export const hermesJsonCatalog=defineCatalog(schema,{
 components:{
  Stack:{props:z.object({}),description:'Vertical layout'},
  Text:{props:z.object({text:z.string()}),description:'Paragraph'},
  Input:{props:z.object({label:z.string(),value:z.string().nullable()}),description:'Text field; bind value using $bindState'},
  Button:{props:z.object({label:z.string()}),description:'Button emitting press'},
 },
 actions:{add_task:{params:z.object({task:z.string()}),description:'Add a demo task locally'}}
});
export function validateJsonSurface(spec:any){
 const checked=hermesJsonCatalog.validate(spec);
 if(!checked.success) throw Error('Invalid Hermes JSON surface: '+checked.error.message);
 const structural=validateSpec(spec);
 if(!structural.valid) throw Error('Invalid Hermes JSON references');
 if(Object.keys(spec.elements).length>200) throw Error('Too many Hermes JSON elements');
 const visit=(id:string,parents:Set<string>)=>{
  if(parents.has(id)) throw Error('Cyclic Hermes JSON reference');
  const node=spec.elements[id];
  for(const bindings of Object.values(node.on ?? {}) as any[]){
   for(const action of Array.isArray(bindings)?bindings:[bindings]){
    if(action.action!=='add_task') throw Error('Unsupported Hermes JSON action');
   }
  }
  for(const child of node.children ?? []) visit(child,new Set([...parents,id]));
 };
 for(const id of Object.keys(spec.elements)) visit(id,new Set());
 return spec;
}
const {registry}=defineRegistry(hermesJsonCatalog,{
  components:{
   Stack:({children})=><div style={{display:'grid',gap:16}}>{children}</div>,
   Text:({props})=>{hermesJsonCatalog.data.components.Text.props.parse(props);return <p>{props.text}</p>;},
   Input:({props,bindings})=>{
    hermesJsonCatalog.data.components.Input.props.parse(props);
    const [value,setValue]=useBoundProp(props.value,bindings?.value);
    return <label style={{display:'grid',gap:8}}>{props.label}<input value={value ?? ''} onChange={e=>setValue(e.target.value)} style={{font:'inherit',padding:10,border:'1px solid',borderRadius:8}}/></label>;
   },
   Button:({props,emit})=>{hermesJsonCatalog.data.components.Button.props.parse(props);return <button type='button' style={{font:'inherit',padding:'10px 16px',cursor:'pointer'}} onClick={()=>emit('press')}>{props.label}</button>;}
  },
  actions:{add_task:async()=>{}}
 });
export function JsonSurface({spec,onAction}:{spec:any;onAction:(name:string,params:any)=>void}){
 validateJsonSurface(spec);
 return <div data-hermes-json-render><JSONUIProvider registry={registry} handlers={{add_task:async(params)=>onAction('add_task',hermesJsonCatalog.data.actions.add_task.params.parse(params))}} initialState={spec.state ?? {}}><Renderer spec={spec} registry={registry}/></JSONUIProvider></div>;
}
