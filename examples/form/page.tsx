import React, {useState} from 'react';
import {Page} from 'grok/canvas';
export default function Example(){const [name,setName]=useState('');const [sent,setSent]=useState(false);return <Page title="Sample form"><form onSubmit={e=>{e.preventDefault();setSent(Boolean(name.trim()))}}><label>Name<input required aria-label="Name" value={name} onChange={e=>setName(e.target.value)}/></label><button type="submit">Submit</button><output>{sent?'Hello, '+name:'Ready'}</output></form></Page>}
