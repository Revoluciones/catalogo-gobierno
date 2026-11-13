import {decode} from 'turbo-stream';
import fs from 'fs';
const buf=fs.readFileSync(process.argv[2]);
const stream=new ReadableStream({start(c){c.enqueue(new Uint8Array(buf));c.close();}});
const r=await decode(stream);
await r.done;
const res=async v=>{ if(v&&typeof v.then==='function') v=await v; if(Array.isArray(v)) return Promise.all(v.map(res)); if(v&&typeof v==='object'&&!(v instanceof Date)){const o={};for(const[k,x] of Object.entries(v))o[k]=await res(x);return o;} return v;};
console.log(JSON.stringify(await res(r.value),null,1));
