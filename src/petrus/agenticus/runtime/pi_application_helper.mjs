/* Pi 0.83.0 application-owned, one-turn low-level-loop bridge. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";

process.umask(0o077);
const METHODS=["workspace_read","workspace_search","workspace_shell","workspace_write","workspace_test"];
const SCHEMAS={
  workspace_read:{type:"object",properties:{path:{type:"string",minLength:1,maxLength:64}},required:["path"],additionalProperties:false},
  workspace_search:{type:"object",properties:{query:{type:"string",minLength:1,maxLength:64},path:{type:"string",minLength:1,maxLength:64}},required:["query","path"],additionalProperties:false},
  workspace_shell:{type:"object",properties:{argv:{type:"array",minItems:1,maxItems:4,items:{type:"string",minLength:1,maxLength:64}},cwd:{type:"string",minLength:1,maxLength:8}},required:["argv","cwd"],additionalProperties:false},
  workspace_write:{type:"object",properties:{path:{type:"string",minLength:1,maxLength:64},content:{type:"string",maxLength:1024}},required:["path","content"],additionalProperties:false},
  workspace_test:{type:"object",properties:{},additionalProperties:false},
};
let frameLimit=16*1024*1024,eventLimit=10000,eventCount=0;
const send=value=>{const line=JSON.stringify(value);if(Buffer.byteLength(line)+1>frameLimit||++eventCount>eventLimit)throw new Error("protocol-failed");process.stdout.write(line+"\n");};
const fail=code=>{try{send({type:"failed",code});}catch(_){}process.exitCode=1;};
const exactObject=(value,keys)=>value&&!Array.isArray(value)&&typeof value==="object"&&Object.keys(value).sort().join()===keys.slice().sort().join();
const positive=value=>Number.isSafeInteger(value)&&value>0;
const ERRORS=new Set(["capability","path","argv","write","unknown","deadline","aborted","stale_epoch","post_fence","provider","schema","authority","budget"]);
const modelResult=value=>exactObject(value,["version","ok","data","error"])&&value.version===1&&typeof value.ok==="boolean"&&(value.ok?(value.data&&!Array.isArray(value.data)&&typeof value.data==="object"&&value.error===null):(value.data===null&&exactObject(value.error,["category","detail"])&&ERRORS.has(value.error.category)&&typeof value.error.detail==="string"&&value.error.detail.length>0&&Buffer.byteLength(value.error.detail)<=128&&!/[\x00-\x1f]/.test(value.error.detail)));
const [codingPath,corePath,aiPath]=process.argv.slice(2,5);
let forcedFailure=null;
try {
  if([codingPath,corePath,aiPath].some(value=>!value||!path.isAbsolute(value)))throw new Error("protocol-failed");
  const coding=await import(codingPath),core=await import(corePath),ai=await import(aiPath);
  if(typeof coding.ModelRuntime?.create!=="function"||typeof coding.convertToLlm!=="function"||typeof core.runAgentLoop!=="function"||typeof ai.createProvider!=="function")throw new Error("protocol-failed");
  if(process.argv[5]==="--test-probe"){
    /* Credential-free exact-core seam: no ModelRuntime/provider authority is
       created, and the injected stream performs no I/O. */
    const prior=[{role:"user",content:[{type:"text",text:"prior"}],timestamp:0}],snapshot=JSON.stringify(prior);
    let calls=0,contextOk=false,network=false;
    const stream=(_model,context)=>{
      calls++;contextOk=JSON.stringify(context.messages.slice(0,-1))===snapshot&&context.messages.at(-1)?.role==="user";
      const message={role:"assistant",content:[{type:"text",text:"delta"}],api:"anthropic-messages",provider:"anthropic",model:"claude-sonnet-4-5",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:"stop",timestamp:0};
      const events=ai.createAssistantMessageEventStream();
      queueMicrotask(()=>{events.push({type:"start",partial:message});events.push({type:"done",reason:"stop",message});events.end(message);});
      return events;
    };
    const delta=await core.runAgentLoop(
      [{role:"user",content:[{type:"text",text:"probe"}],timestamp:0}],
      {systemPrompt:"probe",messages:prior,tools:[]},
      {model:{api:"anthropic-messages",provider:"anthropic",id:"claude-sonnet-4-5"},tools:[],convertToLlm:coding.convertToLlm,shouldStopAfterTurn:()=>true},
      ()=>{},
      new AbortController().signal,
      stream,
    );
    if(!Array.isArray(delta)||delta.length!==2||delta[0]?.role!=="user"||delta[1]?.role!=="assistant")throw new Error("protocol-failed");
    send({type:"test-probe",ok:true,stream_calls:calls,context_ok:contextOk,prior_immutable:JSON.stringify(prior)===snapshot,delta_only:delta.length===2,network});
  }else if(process.argv[5]==="--probe"){
    const catalog=JSON.parse(process.argv[6]||"null");
    if(!Array.isArray(catalog)||!catalog.length||catalog.some(pair=>!Array.isArray(pair)||pair.length!==2||pair.some(x=>typeof x!=="string"||!x)))throw new Error("protocol-failed");
    const root=fs.mkdtempSync(path.join(os.tmpdir(),"petrus-pi-app-probe-"));fs.chmodSync(root,0o700);
    try{const runtime=await coding.ModelRuntime.create({authPath:path.join(root,"auth.json"),modelsPath:null,allowModelNetwork:false});if(catalog.some(([provider,id])=>!runtime.getModel(provider,id)))throw new Error("protocol-failed");}finally{fs.rmSync(root,{recursive:true,force:true});}
    send({type:"probe",ok:true});
  }else{
    const reader=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
    const waiting=new Map();const controller=new AbortController();let startResolve,startReject,first=true,stopping=false;
    const startPromise=new Promise((resolve,reject)=>{startResolve=resolve;startReject=reject;});
    reader.on("line",line=>{try{
      if(Buffer.byteLength(line)>frameLimit)throw new Error();const frame=JSON.parse(line);if(!frame||Array.isArray(frame)||typeof frame!=="object")throw new Error();
      if(first){first=false;startResolve(frame);return;}
      if(exactObject(frame,["type"])&&frame.type==="abort"){stopping=true;controller.abort();for(const pending of waiting.values())pending.reject(new Error("aborted"));waiting.clear();return;}
      if(exactObject(frame,["type","id","result"])&&frame.type==="tool_result"&&waiting.has(frame.id)&&modelResult(frame.result)){const pending=waiting.get(frame.id);waiting.delete(frame.id);pending.resolve(frame.result);return;}
      throw new Error();
    }catch(_){forcedFailure="protocol-failed";controller.abort();for(const pending of waiting.values())pending.reject(new Error("protocol-failed"));waiting.clear();startReject(new Error("protocol-failed"));reader.close();}});
    const start=await startPromise;
    if(!exactObject(start,["api_key","cwd","limits","model","observation","provider","transcript","type","version","write_allowed"])||start.type!=="start"||start.version!==1||typeof start.api_key!=="string"||!start.api_key||typeof start.observation!=="string"||!start.observation||typeof start.write_allowed!=="boolean"||!path.isAbsolute(start.cwd)||!exactObject(start.limits,["frame","output","transcript","messages","events","tools"])||Object.values(start.limits).some(value=>!positive(value)))throw new Error("protocol-failed");
    frameLimit=start.limits.frame;eventLimit=start.limits.events;
    const prior=Buffer.from(start.transcript,"base64");if(prior.length>start.limits.transcript||prior.toString("base64")!==start.transcript)throw new Error("protocol-failed");
    const messages=JSON.parse(prior.toString("utf8"));if(!Array.isArray(messages)||messages.length>=start.limits.messages||messages.some(x=>!x||Array.isArray(x)||typeof x!=="object"))throw new Error("protocol-failed");
    const prompt={role:"user",content:[{type:"text",text:start.observation}],timestamp:Date.now()};
    const root=fs.mkdtempSync(path.join(process.env.HOME,"app-"));fs.chmodSync(root,0o700);
    try {
      const runtime=await coding.ModelRuntime.create({authPath:path.join(root,"auth.json"),modelsPath:null,allowModelNetwork:false});await runtime.setRuntimeApiKey(start.provider,start.api_key);
      const model=runtime.getModel(start.provider,start.model);if(!model||model.provider!==start.provider||model.id!==start.model)throw new Error("provider-failed");
      let calls=0;
      const tools=METHODS.map(name=>({name,label:name,description:"Agenticus workspace capability",parameters:SCHEMAS[name],execute:async(toolCallId,params,signal)=>{
        if(stopping){forcedFailure="aborted";controller.abort();throw new Error("aborted");}
        if(controller.signal.aborted){forcedFailure??="protocol-failed";throw new Error(forcedFailure);}
        if(++calls>start.limits.tools){forcedFailure="protocol-failed";controller.abort();throw new Error("protocol-failed");}
        if(name==="workspace_write"&&!start.write_allowed){forcedFailure="protocol-failed";controller.abort();throw new Error("protocol-failed");}
        if(typeof toolCallId!=="string"||!toolCallId||Buffer.byteLength(toolCallId)>128||waiting.has(toolCallId)){forcedFailure="protocol-failed";controller.abort();throw new Error("protocol-failed");}
        send({type:"tool_call",id:toolCallId,method:name,params});
        const result=await new Promise((resolve,reject)=>{const abort=()=>{waiting.delete(toolCallId);reject(new Error("aborted"));};controller.signal.addEventListener("abort",abort,{once:true});signal?.addEventListener("abort",abort,{once:true});waiting.set(toolCallId,{resolve:value=>{controller.signal.removeEventListener("abort",abort);signal?.removeEventListener("abort",abort);resolve(value);},reject});});
        return {content:[{type:"text",text:JSON.stringify(result)}],details:{}};
      }}));
      send({type:"ready"});
      const config={model,tools,convertToLlm:coding.convertToLlm,toolExecution:"sequential",shouldStopAfterTurn:()=>true,beforeToolCall:async({toolCall,args})=>{
        if(toolCall?.name==="workspace_write"&&!start.write_allowed){const id=toolCall.id,params=args;if(typeof id!=="string"||!id||Buffer.byteLength(id)>128||!params||Array.isArray(params)||typeof params!=="object"){forcedFailure="protocol-failed";controller.abort();throw new Error("protocol-failed");}send({type:"guard_blocked",id,method:"workspace_write",params});return {block:true,reason:"application guard blocked workspace write"};}
      }};
      const delta=await core.runAgentLoop([prompt],{systemPrompt:"You are an Agenticus workspace agent. Use only supplied tools.",messages,tools},config,()=>{},controller.signal,runtime.streamSimple.bind(runtime));
      if(forcedFailure)throw new Error(forcedFailure);if(stopping||controller.signal.aborted)throw new Error("aborted");
      const newMessages=Array.isArray(delta)?delta:Array.isArray(delta?.messages)?delta.messages:null;if(!newMessages?.length||newMessages[0]?.role!=="user")throw new Error("provider-failed");
      const final=[...newMessages].reverse().find(message=>message?.role==="assistant");if(!final||["error","aborted"].includes(final.stopReason))throw new Error(final?.stopReason==="aborted"?"aborted":"provider-failed");
      const text=final.content?.filter(block=>block?.type==="text"&&typeof block.text==="string").map(block=>block.text).join("")??"";
      const encoded=Buffer.from(JSON.stringify(newMessages));if(Buffer.byteLength(text)>start.limits.output||encoded.length>start.limits.transcript||messages.length+newMessages.length>start.limits.messages)throw new Error("protocol-failed");
      send({type:"complete",text,transcript:encoded.toString("base64")});reader.close();
    }finally{controller.abort();fs.rmSync(root,{recursive:true,force:true});}
  }
}catch(error){fail(forcedFailure??(String(error?.message)==="aborted"?"aborted":String(error?.message)==="protocol-failed"?"protocol-failed":"provider-failed"));}
