/* Public Pi 0.83.0 one-model-phase bridge. Declaration-only tools: never execute. */
import path from "node:path";
import readline from "node:readline";

process.umask(0o077);
const LIMITS={frame:16*1024*1024,output:1000000,transcript:4000000,messages:10000};
const CATEGORIES=new Set(["capability","path","argv","write","unknown","deadline","aborted","stale_epoch","post_fence","provider","schema","authority","budget"]);
const METHODS=["workspace_read","workspace_search","workspace_shell","workspace_write","workspace_test"];
const SCHEMAS={
  workspace_read:{type:"object",properties:{path:{type:"string",minLength:1,maxLength:64}},required:["path"],additionalProperties:false},
  workspace_search:{type:"object",properties:{query:{type:"string",minLength:1,maxLength:64},path:{type:"string",minLength:1,maxLength:64}},required:["query","path"],additionalProperties:false},
  workspace_shell:{type:"object",properties:{argv:{type:"array",minItems:1,maxItems:4,items:{type:"string",minLength:1,maxLength:64}},cwd:{type:"string",minLength:1,maxLength:8}},required:["argv","cwd"],additionalProperties:false},
  workspace_write:{type:"object",properties:{path:{type:"string",minLength:1,maxLength:64},content:{type:"string",maxLength:256}},required:["path","content"],additionalProperties:false},
  workspace_test:{type:"object",properties:{},required:[],additionalProperties:false},
};
const object=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
const exact=(v,keys)=>object(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const text=(v,n)=>typeof v==="string"&&v.length>0&&Buffer.byteLength(v)<=n&&v===v.trim()&&![...v].some(c=>c.charCodeAt(0)<32||c.charCodeAt(0)===127);
const prompt=(v,n)=>typeof v==="string"&&v.length>0&&Buffer.byteLength(v)<=n&&!v.includes("\0");
const send=v=>process.stdout.write(JSON.stringify(v)+"\n");
const fail=code=>{try{send({type:"failed",code});}catch{}process.exitCode=1;};
const strictParse=raw=>JSON.parse(raw,(key,value)=>value); // JSON.parse is strict except duplicate names; Python rechecks all output.
const canonical64=value=>{if(typeof value!=="string")throw Error("protocol-failed");const body=Buffer.from(value,"base64");if(body.toString("base64")!==value)throw Error("protocol-failed");return body;};
const validResult=r=>exact(r,["version","ok","data","error"])&&r.version===1&&typeof r.ok==="boolean"&&
  (r.ok?(object(r.data)&&r.error===null):(r.data===null&&exact(r.error,["category","detail"])&&CATEGORIES.has(r.error.category)&&text(r.error.detail,128)));

async function phase(pi,start,runtimeOverride=null) {
  const prior=canonical64(start.transcript);if(prior.length>LIMITS.transcript)throw Error("protocol-failed");
  const messages=strictParse(prior.toString("utf8"));if(!Array.isArray(messages)||messages.length>LIMITS.messages||messages.some(x=>!object(x)))throw Error("protocol-failed");
  const original=JSON.stringify(messages);
  if(start.results.length){
    if(start.observation!==null)throw Error("protocol-failed");
    const assistant=messages.at(-1);if(!exact(assistant,Object.keys(assistant))||assistant.role!=="assistant"||!Array.isArray(assistant.content))throw Error("protocol-failed");
    const calls=assistant.content.filter(x=>object(x)&&x.type==="toolCall");if(calls.length!==start.results.length)throw Error("protocol-failed");
    start.results.forEach((item,i)=>{if(!exact(item,["id","method","result"])||!text(item.id,256)||!text(item.method,256)||item.id!==calls[i].id||item.method!==calls[i].name||!validResult(item.result))throw Error("protocol-failed");
      messages.push({role:"toolResult",toolCallId:item.id,toolName:item.method,content:[{type:"text",text:JSON.stringify(item.result)}],isError:!item.result.ok,timestamp:0});});
  } else if(start.observation!==null) {
    if(!prompt(start.observation,65536))throw Error("protocol-failed");messages.push({role:"user",content:[{type:"text",text:start.observation}],timestamp:0});
  }
  const runtime=runtimeOverride??await pi.ModelRuntime.create({authPath:path.join(process.env.HOME,"auth.json"),modelsPath:null,allowModelNetwork:false});
  await runtime.setRuntimeApiKey(start.provider,start.api_key,{allowNetwork:false});const model=runtime.getModel(start.provider,start.model);if(!model)throw Error("provider-failed");
  const tools=METHODS.map(name=>({name,description:"Agenticus workspace capability",parameters:SCHEMAS[name]}));
  const converted=await pi.convertToLlm(messages);const stream=runtime.streamSimple(model,{systemPrompt:start.system,messages:converted,tools});
  const final=typeof stream.result==="function"?await stream.result():await stream;
  const required=["role","content","api","provider","model","usage","stopReason","timestamp"];
  if(!object(final)||required.some(key=>!Object.hasOwn(final,key))||final.role!=="assistant"||!Array.isArray(final.content)||!object(final.usage)||!text(final.api,256)||!text(final.provider,256)||!text(final.model,256)||!["stop","toolUse","length","error","aborted"].includes(final.stopReason))throw Error("provider-failed");
  if(JSON.stringify(strictParse(prior.toString("utf8")))!==original)throw Error("protocol-failed");
  messages.push(final);const encoded=Buffer.from(JSON.stringify(final));const transcript=Buffer.from(JSON.stringify(messages));
  if(encoded.length>LIMITS.output||transcript.length>LIMITS.transcript||messages.length>LIMITS.messages)throw Error("protocol-failed");
  return {type:"complete",assistant:encoded.toString("base64"),transcript:transcript.toString("base64")};
}

try {
  const entry=process.argv[2];if(!entry||!path.isAbsolute(entry))throw Error("protocol-failed");const pi=await import(entry);
  if(typeof pi.ModelRuntime?.create!=="function"||typeof pi.convertToLlm!=="function")throw Error("protocol-failed");
  if(process.argv[3]==="--probe")send({type:"probe",ok:true});
  else if(process.argv[3]==="--test-probe") {
    let calls=0,convert=false,toolExecute=false;const wrapped={...pi,convertToLlm:async messages=>{convert=true;return pi.convertToLlm(messages);}};
    const runtime={setRuntimeApiKey:async()=>{},getModel:()=>({}),streamSimple:(_model,context)=>{calls++;toolExecute=context.tools.some(tool=>Object.hasOwn(tool,"execute"));return {result:async()=>({role:"assistant",content:[{type:"text",text:"ok"}],api:"anthropic-messages",provider:"anthropic",model:"fake",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:"stop",timestamp:0})};}};
    const start={type:"start",version:1,provider:"anthropic",model:"fake",api_key:"fake",system:"test",observation:"go",transcript:"W10=",results:[],limits:LIMITS};
    const result=await phase(wrapped,start,runtime);send({type:"test-probe",ok:true,stream_calls:calls,convert,tool_execute:toolExecute,network:false,complete:result.type==="complete"});
  } else {
    const reader=readline.createInterface({input:process.stdin,crlfDelay:Infinity});let lines=[];for await(const line of reader){lines.push(line);if(lines.length>1)throw Error("protocol-failed");}
    if(lines.length!==1||Buffer.byteLength(lines[0])>LIMITS.frame)throw Error("protocol-failed");const start=strictParse(lines[0]);
    if(!exact(start,["type","version","provider","model","api_key","system","observation","transcript","results","limits"])||start.type!=="start"||start.version!==1||!text(start.provider,256)||!text(start.model,256)||!text(start.api_key,8192)||!prompt(start.system,65536)||!(start.observation===null||prompt(start.observation,65536))||!Array.isArray(start.results)||start.results.length>16||!exact(start.limits,Object.keys(LIMITS))||Object.keys(LIMITS).some(k=>start.limits[k]!==LIMITS[k]))throw Error("protocol-failed");
    send(await phase(pi,start));reader.close();
  }
} catch(error) { fail(error?.message==="provider-failed"?"provider-failed":"protocol-failed"); }
