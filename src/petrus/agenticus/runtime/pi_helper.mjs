/* Pi 0.83.0 private JSONL bridge. stdout is exclusively the protocol. */
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";

process.umask(0o077);
const METHODS = ["workspace_read", "workspace_search", "workspace_shell", "workspace_write", "workspace_test"];
const SYMBOLS = ["ModelRuntime", "SettingsManager", "DefaultResourceLoader", "SessionManager", "defineTool", "createAgentSession"];
const safeWrite = frame => process.stdout.write(JSON.stringify(frame) + "\n");
const die = (code,extra={}) => { safeWrite({type:"failed",code,...extra}); process.exitCode = 1; };
const fatal = code => process.stdout.write(JSON.stringify({type:"failed",code}) + "\n", () => process.exit(1));
const exactObject=(value,keys)=>value&&!Array.isArray(value)&&typeof value==="object"&&Object.keys(value).sort().join()===keys.slice().sort().join();
const ERRORS=new Set(["capability","path","argv","write","unknown","deadline","aborted","stale_epoch","post_fence","provider","schema","authority","budget"]);
const modelResult=value=>exactObject(value,["version","ok","data","error"])&&value.version===1&&typeof value.ok==="boolean"&&(value.ok?(value.data&&!Array.isArray(value.data)&&typeof value.data==="object"&&value.error===null):(value.data===null&&exactObject(value.error,["category","detail"])&&ERRORS.has(value.error.category)&&typeof value.error.detail==="string"&&value.error.detail.length>0&&Buffer.byteLength(value.error.detail)<=128&&!/[\x00-\x1f]/.test(value.error.detail)));
const readOwned = (file,maximum) => {
  const pathBefore=fs.lstatSync(file);
  if(!pathBefore.isFile()||pathBefore.isSymbolicLink()||pathBefore.uid!==process.geteuid()||(pathBefore.mode&0o777)!==0o600||pathBefore.nlink!==1)throw new Error("auth");
  const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);let before,after,body;
  try{before=fs.fstatSync(fd);if(before.size<=0||before.size>maximum)throw new Error("auth");body=Buffer.alloc(before.size);let n=0;while(n<body.length){const got=fs.readSync(fd,body,n,body.length-n,n);if(!got)break;n+=got;}after=fs.fstatSync(fd);if(n!==body.length)throw new Error("auth");}finally{fs.closeSync(fd);}
  const pathAfter=fs.lstatSync(file);
  if(!before.isFile()||before.uid!==process.geteuid()||(before.mode&0o777)!==0o600||before.nlink!==1||pathBefore.dev!==before.dev||pathBefore.ino!==before.ino||pathBefore.mode!==before.mode||pathBefore.uid!==before.uid||pathBefore.nlink!==before.nlink||pathBefore.size!==before.size||pathBefore.mtimeMs!==before.mtimeMs||before.dev!==after.dev||before.ino!==after.ino||before.mode!==after.mode||before.uid!==after.uid||before.nlink!==after.nlink||before.size!==after.size||before.mtimeMs!==after.mtimeMs||!pathAfter.isFile()||pathAfter.isSymbolicLink()||pathAfter.dev!==after.dev||pathAfter.ino!==after.ino||pathAfter.mode!==after.mode||pathAfter.uid!==after.uid||pathAfter.nlink!==after.nlink||pathAfter.size!==after.size||pathAfter.mtimeMs!==after.mtimeMs)throw new Error("auth");
  return body;
};
const validateNativeAuth = (body,provider) => {
  let stored;try{stored=JSON.parse(body.toString("utf8"));}catch(_){throw new Error("auth");}
  const credential=stored?.[provider];
  if(!stored||Array.isArray(stored)||typeof stored!=="object"||Object.keys(stored).length!==1||Object.keys(stored)[0]!==provider||!credential||Array.isArray(credential)||typeof credential!=="object"||credential.type!=="oauth"||typeof credential.access!=="string"||!credential.access||typeof credential.refresh!=="string"||!credential.refresh||typeof credential.expires!=="number"||!Number.isFinite(credential.expires)||(provider==="openai-codex"&&(typeof credential.accountId!=="string"||!credential.accountId)))throw new Error("auth");
  return body;
};
const sdkPath = process.argv[2];
const extensionPath=process.argv[3]&&!['--probe','--no-extension'].includes(process.argv[3])?process.argv[3]:null;
let nativeAuthPath=null,nativeAuthLimit=0,nativeAuthProvider=null;
const exportNativeAuth=()=>validateNativeAuth(readOwned(nativeAuthPath,nativeAuthLimit),nativeAuthProvider).toString("base64");
const verifyExtensions=result=>{
  const expected=extensionPath?fs.realpathSync(extensionPath):null;
  if(!result||!Array.isArray(result.extensions)||!Array.isArray(result.errors)||result.errors.length||result.extensions.length!==(expected?1:0)||(expected&&result.extensions[0]?.resolvedPath!==expected))throw new Error("extension");
  return expected?result.extensions[0]:null;
};

try {
  if (!sdkPath || !path.isAbsolute(sdkPath)) throw new Error("protocol");
  const sdk = await import(sdkPath);
  if (SYMBOLS.some(name => typeof sdk[name] === "undefined")) throw new Error("symbols");
  if (process.argv[3] === "--probe") {
    const catalog=JSON.parse(process.argv[4]||"null");
    const probeExtensionPath=process.argv[5]?fs.realpathSync(process.argv[5]):null;
    const validCatalog=value=>Array.isArray(value)&&value.length>0&&value.every(pair=>Array.isArray(pair)&&pair.length===2&&pair.every(item=>typeof item==="string"&&item));
    if(!catalog||Array.isArray(catalog)||typeof catalog!=="object"||Object.keys(catalog).sort().join()!=="api_keys,cc_patch_subscriptions,subscriptions"||!validCatalog(catalog.api_keys)||!validCatalog(catalog.subscriptions)||!validCatalog(catalog.cc_patch_subscriptions))throw new Error("protocol");
    const root=fs.mkdtempSync(path.join(os.tmpdir(),"petrus-pi-probe-"));
    fs.chmodSync(root,0o700);
    let session;
    try {
      const runtime=await sdk.ModelRuntime.create({authPath:path.join(root,"api-auth.json"),modelsPath:null,allowModelNetwork:false});
      const models=catalog.api_keys.map(([provider,id])=>runtime.getModel(provider,id));
      if(models.some(model=>!model))throw new Error("symbols");
      for(const [index,[provider,id]] of catalog.subscriptions.entries()){
        const directory=path.join(root,`subscription-${index}`);fs.mkdirSync(directory,{mode:0o700});
        const authPath=path.join(directory,"auth.json");
        const credential={type:"oauth",access:"petrus-nonsecret-probe-access",refresh:"petrus-nonsecret-probe-refresh",expires:Date.now()+86400000,...(provider==="openai-codex"?{accountId:"petrus-nonsecret-probe-account"}:{})};
        fs.writeFileSync(authPath,JSON.stringify({[provider]:credential}),{mode:0o600,flag:"wx"});
        const subscriptionRuntime=await sdk.ModelRuntime.create({authPath,modelsPath:null,allowModelNetwork:false});
        const credentials=await subscriptionRuntime.listCredentials();
        if(!subscriptionRuntime.isUsingOAuth(provider)||credentials.length!==1||credentials[0]?.providerId!==provider||credentials[0]?.type!=="oauth"||!subscriptionRuntime.getModel(provider,id))throw new Error("symbols");
      }
      const malformed=path.join(root,"malformed-auth.json");fs.writeFileSync(malformed,"not-json",{mode:0o600,flag:"wx"});
      const malformedRuntime=await sdk.ModelRuntime.create({authPath:malformed,modelsPath:null,allowModelNetwork:false});
      if(malformedRuntime.isUsingOAuth(catalog.subscriptions[0][0])||(await malformedRuntime.listCredentials()).length)throw new Error("symbols");
      const model=models[0];
      const settings=sdk.SettingsManager.inMemory({retry:{enabled:false},compaction:{enabled:false}});
      const loader=new sdk.DefaultResourceLoader({cwd:root,agentDir:root,settingsManager:settings,noExtensions:true,additionalExtensionPaths:probeExtensionPath?[probeExtensionPath]:[],noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,systemPrompt:"Agenticus probe.",appendSystemPrompt:[]});
      await loader.reload();
      const loaded=loader.getExtensions();
      const expected=probeExtensionPath?fs.realpathSync(probeExtensionPath):null;
      if(loaded.errors.length||loaded.extensions.length!==(expected?1:0)||(expected&&loaded.extensions[0]?.resolvedPath!==expected))throw new Error("extension");
      if(expected){
        const handlers=loaded.extensions[0].handlers?.get("before_provider_request");
        if(!Array.isArray(handlers)||handlers.length!==1)throw new Error("extension");
        const payload={messages:[],system:[{type:"text",text:"You are Claude Code, Anthropic's official CLI for Claude."},{type:"text",text:"You are operating inside pi, a coding agent harness."}]};
        const patched=await handlers[0]({type:"before_provider_request",payload},{model:{provider:"anthropic"}});
        if(patched!==payload||payload.system[0]?.text!=="x-anthropic-billing-header: cc_version=2.1.96.000; cc_entrypoint=cli;"||payload.system.some(block=>block?.text?.includes("official CLI"))||payload.system.some(block=>block?.text?.includes("coding agent harness")))throw new Error("extension");
        const apiKeyPayload={messages:[],system:[{type:"text",text:"You are operating inside pi, a coding agent harness."}]};
        const apiKeyBefore=JSON.stringify(apiKeyPayload),apiKeyResult=await handlers[0]({type:"before_provider_request",payload:apiKeyPayload},{model:{provider:"anthropic"}});
        if(apiKeyResult!==undefined||JSON.stringify(apiKeyPayload)!==apiKeyBefore)throw new Error("extension");
        const routedPayload={model:"anthropic/claude-sonnet-4-5",messages:[],system:[{type:"text",text:"You are Claude Code, Anthropic's official CLI for Claude."}]};
        const routedBefore=JSON.stringify(routedPayload),routedResult=await handlers[0]({type:"before_provider_request",payload:routedPayload},{model:{provider:"openrouter"}});
        if(routedResult!==undefined||JSON.stringify(routedPayload)!==routedBefore)throw new Error("extension");
      }
      const manager=sdk.SessionManager.inMemory(root,{id:crypto.randomUUID()});
      const customTools=METHODS.map(method=>sdk.defineTool({name:method,label:method,description:"Agenticus probe",parameters:{type:"object",properties:{},additionalProperties:false},execute:async()=>({content:[{type:"text",text:"probe"}],details:{}})}));
      ({session}=await sdk.createAgentSession({cwd:root,agentDir:root,modelRuntime:runtime,model,settingsManager:settings,resourceLoader:loader,sessionManager:manager,noTools:"builtin",customTools}));
      if(typeof session.prompt!=="function"||typeof session.waitForIdle!=="function"||typeof session.abort!=="function"||typeof session.dispose!=="function"||typeof session.subscribe!=="function"||!session.state)throw new Error("symbols");
    } finally {
      session?.dispose();
      fs.rmSync(root,{recursive:true,force:true});
    }
    safeWrite({type:"probe", ok:true});
  } else {
    const reader = readline.createInterface({input:process.stdin, crlfDelay:Infinity});
    const waiting = new Map();
    let startResolve, startReject, session;
    const startPromise = new Promise((resolve,reject)=>{ startResolve=resolve; startReject=reject; });
    let first = true, maxFrame = 16*1024*1024, stopping = false;
    reader.on("line", line => {
      try {
        if (Buffer.byteLength(line) > maxFrame) throw new Error("frame");
        const frame = JSON.parse(line);
        if (!frame || Array.isArray(frame) || typeof frame !== "object") throw new Error("frame");
        if (first) { first=false; startResolve(frame); return; }
        if (frame.type === "abort" && Object.keys(frame).length === 1) {
          stopping=true;
          for (const pending of waiting.values()) pending.reject(new Error("aborted"));
          waiting.clear();
          Promise.resolve(session?.abort()).catch(()=>{});
          return;
        }
        if (frame.type === "tool_result" && Object.keys(frame).sort().join() === "id,result,type" && waiting.has(frame.id) && modelResult(frame.result)) {
          const pending=waiting.get(frame.id); waiting.delete(frame.id); pending.resolve(frame.result); return;
        }
        throw new Error("frame");
      } catch (_) {
        stopping=true;
        waiting.clear();
        Promise.resolve(session?.abort()).catch(()=>{});
        reader.close(); fatal("protocol-failed");
      }
    });
    reader.on("close", ()=>{ if(first) startReject(new Error("protocol")); });
    const start = await startPromise;
    const apiKeys = ["api_key","cwd","limits","model","prompt","provider","root","schemas","session","session_id","type","version"];
    const authKeys = ["auth","cwd","limits","model","prompt","provider","root","schemas","session","session_id","type","version"];
    const startKeys=Object.keys(start).sort().join(), apiMode=startKeys===apiKeys.sort().join(), nativeMode=startKeys===authKeys.sort().join();
    if ((!apiMode&&!nativeMode) || (extensionPath&&apiMode) || start.type!=="start" || start.version!==1 ||
        !start.limits || !Number.isSafeInteger(start.limits.frame) || !Number.isSafeInteger(start.limits.output) ||
        !Number.isSafeInteger(start.limits.session) || !Number.isSafeInteger(start.limits.events) || !Number.isSafeInteger(start.limits.tools) ||
        (nativeMode&&(!Number.isSafeInteger(start.limits.auth)||start.limits.auth<=0||!(extensionPath?[["anthropic","claude-sonnet-4-5"]]:[["anthropic","claude-sonnet-4-5"],["openai-codex","gpt-5.6-sol"]]).some(([provider,model])=>provider===start.provider&&model===start.model))) ||
        [start.provider,start.model,start.prompt,start.cwd,start.root,start.session_id].some(x=>typeof x!=="string"||!x) ||
        (apiMode&&(typeof start.api_key!=="string"||!start.api_key)) || (nativeMode&&(typeof start.auth!=="string"||!start.auth)) ||
        !path.isAbsolute(start.cwd) || !path.isAbsolute(start.root) || !crypto.randomUUID ||
        Object.keys(start.schemas).sort().join() !== [...METHODS].sort().join()) throw new Error("protocol");
    maxFrame=start.limits.frame;
    const root=fs.realpathSync(start.root);
    const ownedDir = name => { const p=path.join(root,name); fs.mkdirSync(p,{mode:0o700}); return p; };
    const agentDir=ownedDir("agent"), authDir=ownedDir("auth"), sessionDir=ownedDir("sessions");
    const authPath=path.join(authDir,"auth.json");
    if(nativeMode){
      const body=Buffer.from(start.auth,"base64");
      if(!body.length||body.length>start.limits.auth||body.toString("base64")!==start.auth)throw new Error("auth");
      validateNativeAuth(body,start.provider);
      const fd=fs.openSync(authPath,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
      try{fs.writeFileSync(fd,body);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
      readOwned(authPath,start.limits.auth);
      nativeAuthPath=authPath;nativeAuthLimit=start.limits.auth;nativeAuthProvider=start.provider;
    }
    const runtime=await sdk.ModelRuntime.create({authPath,modelsPath:null,allowModelNetwork:false});
    if(apiMode)await runtime.setRuntimeApiKey(start.provider,start.api_key);
    else{
      const credentials=await runtime.listCredentials();
      if(!runtime.isUsingOAuth(start.provider)||credentials.length!==1||credentials[0]?.providerId!==start.provider||credentials[0]?.type!=="oauth")throw new Error("auth");
    }
    const model=runtime.getModel(start.provider,start.model);
    if (!model || model.provider!==start.provider || model.id!==start.model) throw new Error("model");
    const settings=sdk.SettingsManager.inMemory({retry:{enabled:false},compaction:{enabled:false}});
    const loader=new sdk.DefaultResourceLoader({cwd:start.cwd,agentDir,settingsManager:settings,noExtensions:true,additionalExtensionPaths:extensionPath?[extensionPath]:[],noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,systemPrompt:"You are an Agenticus workspace agent. Use only the supplied tools.",appendSystemPrompt:[]});
    await loader.reload();
    verifyExtensions(loader.getExtensions());
    let manager;
    if(start.session!==null){
      const body=Buffer.from(start.session,"base64");
      if(!body.length||body.length>start.limits.session||body.toString("base64")!==start.session) throw new Error("session");
      const resumed=path.join(sessionDir,"resume.jsonl");
      const fd=fs.openSync(resumed,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
      try{fs.writeFileSync(fd,body);}finally{fs.closeSync(fd);}
      manager=sdk.SessionManager.open(resumed,sessionDir,start.cwd);
    }else{
      manager=sdk.SessionManager.create(start.cwd,sessionDir,{id:start.session_id});
    }
    let calls=0;
    const customTools=METHODS.map(method=>sdk.defineTool({name:method,label:method,description:"Agenticus workspace capability",parameters:start.schemas[method],execute:async(toolCallId,params,signal)=>{
      if(stopping||++calls>start.limits.tools) throw new Error("aborted");
      const encoded=JSON.stringify(params); if(Buffer.byteLength(encoded)>8192) throw new Error("input");
      if(typeof toolCallId!=="string"||!toolCallId||Buffer.byteLength(toolCallId)>128||waiting.has(toolCallId))throw new Error("input");
      const id=toolCallId;
      safeWrite({type:"tool_call",id,method,params});
      const result=await new Promise((resolve,reject)=>{
        const abort=()=>{waiting.delete(id);reject(new Error("aborted"));};
        signal?.addEventListener("abort",abort,{once:true});
        waiting.set(id,{resolve:value=>{signal?.removeEventListener("abort",abort);resolve(value);},reject});
      });
      return {content:[{type:"text",text:JSON.stringify(result)}],details:{}};
    }}));
    ({session}=await sdk.createAgentSession({cwd:start.cwd,agentDir,modelRuntime:runtime,model,settingsManager:settings,resourceLoader:loader,sessionManager:manager,noTools:"builtin",customTools}));
    safeWrite({type:"ready"});
    try {
      if(stopping) throw new Error("aborted");
      let events=0;
      const unsubscribe=session.subscribe(()=>{
        if(++events>start.limits.events){
          stopping=true;
          for (const pending of waiting.values()) pending.reject(new Error("aborted"));
          waiting.clear();
          void session.abort();
        }
      });
      await session.prompt(start.prompt,{expandPromptTemplates:false});
      await session.waitForIdle();
      if(stopping) throw new Error("aborted");
      const messages=session.state?.messages;
      const final=Array.isArray(messages) ? [...messages].reverse().find(m=>m?.role==="assistant") : null;
      if(!final || final.stopReason!=="stop" || !Array.isArray(final.content)) throw new Error("provider");
      const text=final.content.filter(b=>b?.type==="text"&&typeof b.text==="string").map(b=>b.text).join("");
      if(!text || Buffer.byteLength(text)>start.limits.output) throw new Error("provider");
      const file=manager.getSessionFile(); fs.chmodSync(file,0o600);
      const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW); let before,after,body;
      try{before=fs.fstatSync(fd);if(before.size<=0||before.size>start.limits.session)throw new Error("session");body=Buffer.alloc(before.size);let n=0;while(n<body.length){const got=fs.readSync(fd,body,n,body.length-n,n);if(!got)break;n+=got;}after=fs.fstatSync(fd);if(n!==body.length)throw new Error("session");}finally{fs.closeSync(fd);}
      if(!before.isFile()||before.uid!==process.geteuid()||(before.mode&0o777)!==0o600||before.nlink!==1||before.dev!==after.dev||before.ino!==after.ino||before.size!==after.size||before.mtimeMs!==after.mtimeMs)throw new Error("session");
      const lines=body.toString("utf8").split("\n"); if(lines.at(-1)!=="")throw new Error("session"); lines.pop();
      const entries=lines.map(JSON.parse), headers=entries.filter(x=>x?.type==="session");
      if(!entries.length||entries.length>start.limits.events||headers.length!==1||entries[0].type!=="session"||entries[0].version!==3||entries[0].id!==start.session_id)throw new Error("session");
      safeWrite({type:"complete",session_id:start.session_id,text,session:body.toString("base64"),...(nativeAuthPath?{auth:exportNativeAuth()}:{})});
      unsubscribe();
    } finally {
      if(stopping) await session.abort();
      session.dispose();
      reader.close();
    }
  }
} catch (error) {
  const message=String(error?.message);
  let code=message==="aborted"?"aborted":message==="session"?"session-invalid":["protocol","auth"].includes(message)?"protocol-failed":"provider-failed";
  let extra={};
  if(code==="provider-failed"&&nativeAuthPath){try{extra={auth:exportNativeAuth()};}catch(_){code="protocol-failed";}}
  die(code,extra);
}
