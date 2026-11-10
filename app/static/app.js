const $ = id => document.getElementById(id);
let exercises = [], conversations = [], selected = null, selectedConversation = null, conversationState = null;
let eventSource = null, toastTimer = null;
let geminiConfigured = false, gnaniConfigured = false, aiActive = false, aiBusy = false;
let aiUserTurns = 0, aiHistory = [], aiAudio = null, aiSpeechController = null;
let liveCaptureTarget = "practice";
const iconSet = ["◉","↗","〰","✧"];
const seenEvents = new Set();

async function api(path, options={}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await response.json().catch(()=>({error:"The server returned an invalid response"}));
  if (!response.ok) {
    const detail=data.detail??data.error;
    const message=typeof detail==="string"?detail:Array.isArray(detail)?detail.map(item=>item.msg).join("; "):"";
    throw new Error(message||`Request failed (${response.status})`);
  }
  return data;
}
function notify(message){
  $("toast").textContent=message; $("toast").classList.add("show");
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>$ ("toast").classList.remove("show"),2600);
}
function showTab(name){
  document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));
  document.querySelectorAll(".panel").forEach(p=>p.classList.toggle("active",p.id===name));
  $("crumb-current").textContent=name.toUpperCase();
  if(name==="progress") loadSessions();
}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.tab)));

async function init(){
  try{
    const [health,list,roleplays,gnani,gemini]=await Promise.all([api("/api/health"),api("/api/exercises"),api("/api/conversations"),api("/api/gnani/status"),api("/api/gemini/status")]);
    $("mode").textContent=gnani.configured?"Gnani key configured":"Gnani unavailable";
    $("mode").title=gnani.message;
    $("provider-tag").textContent=gnani.configured?`${gnani.models.speech_to_text} · access unverified`:"GNANI: KEY REQUIRED";
    gnaniConfigured=gnani.configured;
    updateCaptureButtons(false);
    $("speak-target").title=gnani.configured?"Play a Gnani-generated example":"Configure Gnani API access";
    geminiConfigured=gemini.configured;
    $("gemini-status").textContent=gemini.configured?`${gemini.model} · access unverified`:"GEMINI KEY REQUIRED";
    $("gemini-status").title=gemini.message;
    $("ai-start").disabled=!gemini.configured||!gnani.configured;
    $("ai-start").title=!gnani.configured?"Configure Gnani for speech services":gemini.message;
    const missingProviders=[];
    if(!gemini.configured)missingProviders.push("GEMINI_API_KEY");
    if(!gnani.configured)missingProviders.push("GNANI_API_KEY");
    $("ai-setup-note").textContent=missingProviders.length
      ?`Add ${missingProviders.join(" and ")} to your local .env and restart the app to enable voice conversations.`
      :"Keys are set. The first AI turn will verify provider access.";
    $("ai-setup-note").classList.toggle("hidden",gemini.configured&&gnani.configured);
    conversations=roleplays.conversations;
    conversations.forEach(item=>{
      const option=document.createElement("option");option.value=item.id;option.textContent=item.title;
      $("ai-scenario").append(option);
    });
    exercises=list.exercises;renderExercises();renderConversations();connectEvents();
  }catch(e){$("mode").textContent="Unavailable";setConnection(false);notify(e.message);}
}
function renderExercises(){
  const grid=$("exercise-grid"); grid.replaceChildren();
  exercises.forEach((e,i)=>{
    const b=document.createElement("button");b.className="exercise"+(selected?.id===e.id?" selected":"");b.type="button";
    const icon=document.createElement("div");icon.className="exercise-icon";icon.textContent=iconSet[i%iconSet.length];
    const arrow=document.createElement("span");arrow.className="arrow";arrow.textContent="↗";
    const title=document.createElement("h3");title.textContent=e.title;
    const meta=document.createElement("p");meta.textContent=`${e.level} · ${e.duration}`;
    b.append(icon,arrow,title,meta);b.addEventListener("click",()=>selectExercise(e.id));grid.append(b);
  });
}
function renderConversations(){
  const grid=$("conversation-grid");grid.replaceChildren();
  conversations.forEach((conversation,i)=>{
    const b=document.createElement("button");b.className="exercise conversation"+(selectedConversation?.id===conversation.id?" selected":"");b.type="button";
    const icon=document.createElement("div");icon.className="exercise-icon";icon.textContent=iconSet[(i+1)%iconSet.length];
    const arrow=document.createElement("span");arrow.className="arrow";arrow.textContent="↗";
    const title=document.createElement("h3");title.textContent=conversation.title;
    const meta=document.createElement("p");meta.textContent=`${conversation.category} · ${conversation.duration}`;
    b.append(icon,arrow,title,meta);b.addEventListener("click",()=>selectConversation(conversation.id));grid.append(b);
  });
}
function selectExercise(id){
  selected=exercises.find(e=>e.id===id);selectedConversation=null;conversationState=null;
  stopLiveCapture(false);renderExercises();renderConversations();
  $("practice-card").classList.remove("hidden");$("exercise-title").textContent=selected.title;
  $("exercise-level").textContent=selected.level;$("exercise-tip").textContent=selected.tip;
  $("conversation-step").classList.add("hidden");$("prompt-label").textContent="YOUR SPEAKING PROMPT";
  $("speak-target").innerHTML="<span>▶</span> Listen to example";
  $("transcript-label").textContent="What did you say?";
  $("practice-helper").textContent="Live mode: microphone audio streams continuously to Gnani Prisma. No browser speech-recognition fallback is used.";
  $("submit-practice").innerHTML="Review practice <span>↗</span>";
  $("target-text").textContent=selected.target;$("transcript").value="";$("feedback").classList.add("hidden");
  updateTranscriptState();
  $("practice-card").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"});
}
function selectConversation(id){
  selected=null;selectedConversation=conversations.find(item=>item.id===id);
  conversationState={index:0,turns:[],completed:false};stopLiveCapture(false);
  renderExercises();renderConversations();
  $("practice-card").classList.remove("hidden");$("exercise-title").textContent=selectedConversation.title;
  $("exercise-level").textContent=`${selectedConversation.level} · ${selectedConversation.turns.length} turns`;
  $("exercise-tip").textContent=`Scenario: ${selectedConversation.situation}`;
  $("conversation-step").classList.remove("hidden");$("prompt-label").textContent="PARTNER SAYS";
  $("speak-target").innerHTML="<span>▶</span> Listen to partner";
  $("transcript-label").textContent="Your response";
  $("practice-helper").textContent="Speak naturally or type your response. Each turn stays on this device until you finish and save the role-play.";
  $("feedback").classList.add("hidden");$("transcript").value="";
  renderConversationTurn();updateTranscriptState();
  $("practice-card").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"});
}
function renderConversationTurn(){
  const turn=selectedConversation.turns[conversationState.index];
  const total=selectedConversation.turns.length;
  $("turn-count").textContent=`TURN ${conversationState.index+1} OF ${total}`;
  $("turn-progress").style.width=`${((conversationState.index+1)/total)*100}%`;
  $("conversation-step").querySelector(".turn-progress").setAttribute("aria-valuenow",conversationState.index+1);
  $("turn-goal").textContent=turn.goal;$("turn-starter").textContent=turn.starter;
  $("target-text").textContent=turn.partner;
}
function updateTranscriptState(){
  const transcript=$("transcript").value;
  $("transcript-count").textContent=`${transcript.length.toLocaleString()} / 2,000`;
  const button=$("submit-practice");
  button.disabled=!transcript.trim()||button.dataset.submitting==="true"||conversationState?.completed===true;
  if(conversationState){
    button.textContent=conversationState.completed?"Conversation saved":
      conversationState.index===selectedConversation.turns.length-1?"Finish conversation ↗":"Save turn & continue ↗";
  }else if(selected){
    button.innerHTML="Review practice <span>↗</span>";
  }
}
$("transcript").addEventListener("input",updateTranscriptState);

$("speak-target").addEventListener("click",async()=>{
  if(!selected&&!selectedConversation)return;
  const button=$("speak-target");button.disabled=true;
  try{
    const response=await fetch("/api/gnani/speak",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:$("target-text").textContent,language:$("speech-language").value})});
    if(!response.ok){const err=await response.json().catch(()=>({}));throw new Error(err.detail||err.error||"Gnani speech service unavailable");}
    const blob=await response.blob();const url=URL.createObjectURL(blob);const audio=new Audio(url);
    audio.onended=()=>URL.revokeObjectURL(url);audio.onerror=()=>{URL.revokeObjectURL(url);notify("Could not play the generated audio.");};await audio.play();
  }catch(e){
    notify(e.message);
  }finally{button.disabled=false;}
});

// True live Prisma streaming: browser captures mono PCM16 at 16 kHz and sends
// exact 1,024-byte frames at the audio callback cadence. No browser STT fallback.
let liveAudio = null, liveSocket = null, liveProcessor = null, liveSource = null, livePrismaReady = false;
let pcmQueue = new Int16Array(0), liveStream = null, liveStarting = false, liveStopping = false, liveStopRequested = false;
const MAX_PENDING_SAMPLES=16000*12;
function appendTranscript(text){
  const area=$("transcript"); area.value=(area.value ? area.value+" " : "")+text;
  area.dispatchEvent(new Event("input",{bubbles:true}));
}
function appendAiTranscript(text){
  const area=$("ai-input");area.value=(area.value ? area.value+" " : "")+text;
  updateAiControls();
}
function updateCaptureButtons(recording=false){
  const starting=recording||liveStarting||liveStopping;
  $("record-start").disabled=starting||!gnaniConfigured;
  $("record-start").textContent=liveStarting?"Connecting…":recording?(livePrismaReady?"● Listening":"● Listening · Connecting"):"● Start live Prisma";
  $("record-stop").disabled=!recording;
  $("ai-record-start").disabled=starting||!aiActive||!gnaniConfigured;
  $("ai-record-start").textContent=liveStarting?"Connecting…":recording?(livePrismaReady?"● Listening":"● Listening · Connecting"):"● Speak";
  $("ai-record-stop").disabled=liveCaptureTarget!=="chat"||!liveAudio;
}
function flushPcmQueue(socket,force=false){
  while(pcmQueue.length>=512&&socket.readyState===WebSocket.OPEN&&(force||socket.bufferedAmount<65536)){
    socket.send(pcmQueue.slice(0,512).buffer);pcmQueue=pcmQueue.slice(512);
  }
}
function requestPrismaStop(socket){
  if(!socket || socket.readyState !== WebSocket.OPEN){
    liveStopping=false;
    liveStopRequested=false;
    return;
  }
  liveStopping=true;liveStopRequested=false;
  socket.send(JSON.stringify({type:"stop"}));
  const timeout=setTimeout(()=>{if(socket.readyState===WebSocket.OPEN)socket.close(1000,"Stop timeout");},5000);
  socket.addEventListener("close",()=>clearTimeout(timeout),{once:true});
}
async function startPrismaCapture(target="practice"){
  if(target==="practice"&&!selected&&!selectedConversation){notify("Choose an exercise first.");return;}
  if(target==="chat"&&(!aiActive||aiBusy)){notify("Wait for the Gemini turn to finish first.");return;}
  if(liveStarting||liveStream||liveAudio||liveSocket)return;
  liveCaptureTarget=target;
  livePrismaReady=false;
  liveStarting=true;updateCaptureButtons(false);
  $("connection").textContent="● Connecting to Prisma";
  notify("Preparing your microphone and connecting to Prisma…");
  try{
    liveAudio=new (window.AudioContext||window.webkitAudioContext)({sampleRate:16000});
    const audioContext=liveAudio;
    if(audioContext.sampleRate!==16000) throw new Error("This browser could not open a 16 kHz audio context. Try a supported desktop browser.");
    const audioReady=audioContext.resume();
    const streamReady=navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}})
      .then(stream=>{
        if(!liveStarting){stream.getTracks().forEach(track=>track.stop());throw new Error("Microphone start was cancelled.");}
        liveStream=stream;return stream;
      });
    const scheme=location.protocol==="https:"?"wss":"ws";
    liveSocket=new WebSocket(`${scheme}://${location.host}/ws/prisma?language=${encodeURIComponent($("speech-language").value)}`);
    const socket=liveSocket;
    let prismaReady=false;
    socket.binaryType="arraybuffer";
    socket.onmessage=e=>{
      const data=JSON.parse(e.data);
      if(data.type==="ready"){prismaReady=true;livePrismaReady=true;updateCaptureButtons(Boolean(liveAudio));$("connection").textContent="● Prisma ready";if(liveProcessor)flushPcmQueue(socket,true);}
      else if(data.type==="transcript"){
        if(liveCaptureTarget==="chat")appendAiTranscript(data.text);else appendTranscript(data.text);
        notify(`Live transcript received${data.latency_ms!=null?` · ${data.latency_ms} ms`:''}`);
      }
      else if(data.type==="processing"){ $("connection").textContent="● Processing speech"; }
      else if(data.type==="error"){notify(data.message||"Prisma streaming error.");}
      else if(data.type==="complete"){
        $("connection").textContent="● Transcript ready";
        if(liveCaptureTarget==="chat")notify("Transcript ready. Send it to Gemini when you are ready.");
        else notify("Prisma session completed.");
        socket.close(1000,"Prisma session complete");
      }
    };
    socket.onerror=()=>notify("Live Prisma connection failed. Check credentials and network.");
    socket.onclose=()=>{
      if(liveStream||liveAudio||liveProcessor)stopLiveCapture(false);
      if(liveSocket===socket)liveSocket=null;
      livePrismaReady=false;
      pcmQueue=new Int16Array(0);liveStopRequested=false;liveStopping=false;
      updateCaptureButtons(false);
    };
    const socketReady=new Promise((resolve,reject)=>{
      let settled=false;
      const cleanup=()=>{
        clearTimeout(timeout);
        socket.removeEventListener("message",onReady);
        socket.removeEventListener("error",onError);
        socket.removeEventListener("close",onClose);
      };
      const finish=error=>{
        if(settled)return;
        settled=true;cleanup();
        if(error)reject(error);else resolve();
      };
      const onReady=e=>{
        try{
          const data=JSON.parse(e.data);
          if(data.type==="ready")finish();
          else if(data.type==="error")finish(new Error(data.message||"Prisma streaming error."));
        }catch(error){finish(error);}
      };
      const onError=()=>finish(new Error("Could not connect to Prisma."));
      const onClose=()=>finish(new Error("Prisma connection closed before it was ready."));
      const timeout=setTimeout(()=>finish(new Error("Prisma connection timed out.")),12000);
      socket.addEventListener("message",onReady);
      socket.addEventListener("error",onError);
      socket.addEventListener("close",onClose);
    });
    socketReady.catch(()=>{});
    await Promise.all([streamReady,audioReady]);
    if(!liveStarting)return;
    const processor=audioContext.createScriptProcessor(512,1,1);
    const mute=liveAudio.createGain();mute.gain.value=0;
    liveSource=liveAudio.createMediaStreamSource(liveStream);
    processor.onaudioprocess=event=>{
      const input=event.inputBuffer.getChannelData(0);
      const pcm=new Int16Array(input.length);
      for(let i=0;i<input.length;i++){const v=Math.max(-1,Math.min(1,input[i]));pcm[i]=v<0?v*32768:v*32767;}
      const joined=new Int16Array(pcmQueue.length+pcm.length);joined.set(pcmQueue);joined.set(pcm,pcmQueue.length);pcmQueue=joined;
      if(pcmQueue.length>MAX_PENDING_SAMPLES)pcmQueue=pcmQueue.slice(pcmQueue.length-MAX_PENDING_SAMPLES);
      if(liveSocket===socket&&socket.readyState===WebSocket.OPEN)flushPcmQueue(socket);
    };
    liveSource.connect(processor);processor.connect(mute);mute.connect(audioContext.destination);liveProcessor=processor;
    liveStarting=false;
    updateCaptureButtons(true);
    if(prismaReady){flushPcmQueue(socket,true);$("connection").textContent="● Live sync";}
    else{$("connection").textContent="● Connecting to Prisma";notify("Microphone ready. Speak now while Prisma connects.");}
    await socketReady;
    if(liveSocket!==socket)return;
    flushPcmQueue(socket,true);
    if(liveStopRequested){
      requestPrismaStop(socket);liveSocket=null;pcmQueue=new Int16Array(0);
      return;
    }
    $("connection").textContent="● Live sync";
    notify("Connected to Gnani Prisma. Speech is streaming.");
  }catch(e){liveStarting=false;notify(e.message);stopLiveCapture(false);}
}
 $("record-start").addEventListener("click",()=>startPrismaCapture("practice"));
 $("ai-record-start").addEventListener("click",()=>startPrismaCapture("chat"));
function stopLiveCapture(sendStop=true){
  liveStarting=false;
  if(liveProcessor){liveProcessor.disconnect();liveProcessor.onaudioprocess=null;liveProcessor=null;}
  if(liveSource){liveSource.disconnect();liveSource=null;}
  if(liveStream){liveStream.getTracks().forEach(t=>t.stop());liveStream=null;}
  if(liveAudio){liveAudio.close().catch(()=>{});liveAudio=null;}
  if(liveSocket&&[WebSocket.OPEN,WebSocket.CONNECTING].includes(liveSocket.readyState)){
    const socket=liveSocket;
    if(sendStop&&socket.readyState===WebSocket.OPEN){
      flushPcmQueue(socket,true);requestPrismaStop(socket);liveSocket=null;pcmQueue=new Int16Array(0);
    }else if(sendStop&&socket.readyState===WebSocket.CONNECTING){
      liveStopRequested=true;liveStopping=true;
    }else{
      socket.close(1000,"Capture cancelled");
      liveSocket=null;liveStopRequested=false;pcmQueue=new Int16Array(0);
    }
  }else{
    liveSocket=null;liveStopRequested=false;pcmQueue=new Int16Array(0);
  }
  updateCaptureButtons(false);
}
$("record-stop").addEventListener("click",()=>{stopLiveCapture(true);notify("Live session stopped.");});
$("ai-record-stop").addEventListener("click",()=>{stopLiveCapture(true);$("connection").textContent="● Finalizing transcript";notify("Finishing your transcript…");});
function addAiMessage(role,text){
  const message=document.createElement("div");message.className=`chat-message ${role}`;
  const label=document.createElement("small");label.textContent=role==="user"?"You":"Gemini";
  const content=document.createElement("div");content.textContent=text;
  message.append(label,content);$("ai-thread").append(message);$("ai-thread").scrollTop=$("ai-thread").scrollHeight;
  return message;
}
function updateAiControls(){
  const input=$("ai-input");
  $("ai-send").disabled=!aiActive||aiBusy||!input.value.trim();
  $("ai-send").textContent=aiBusy?"Gemini is replying…":"Send to Gemini ↗";
  $("ai-save").disabled=!aiActive||aiBusy||aiUserTurns===0;
  $("ai-record-start").disabled=!aiActive||aiBusy||!gnaniConfigured||liveStarting||Boolean(liveAudio);
  $("ai-record-stop").disabled=liveCaptureTarget!=="chat"||!liveAudio;
}
function stopAiSpeech(){
  if(aiSpeechController){aiSpeechController.abort();aiSpeechController=null;}
  if(aiAudio){aiAudio.pause();URL.revokeObjectURL(aiAudio.src);aiAudio=null;}
}
async function speakAiReply(text){
  stopAiSpeech();
  const controller=new AbortController();aiSpeechController=controller;
  try{
    const response=await fetch("/api/gnani/speak",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text,language:$("speech-language").value}),signal:controller.signal});
    if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(error.detail||"Gnani speech playback failed.");}
    if(controller.signal.aborted)return;
    const blob=await response.blob();
    if(controller.signal.aborted)return;
    const url=URL.createObjectURL(blob);
    aiAudio=new Audio(url);
    const audio=aiAudio;
    const cleanup=()=>{URL.revokeObjectURL(url);if(aiAudio===audio)aiAudio=null;};
    audio.onended=cleanup;
    audio.onerror=()=>{cleanup();notify("Gemini replied in text, but Gnani could not play the audio.");};
    await audio.play();
  }catch(error){if(error.name!=="AbortError")notify(error.message);}
  finally{if(aiSpeechController===controller)aiSpeechController=null;}
}
async function requestGemini(action,history=[],onChunk=()=>{}){
  const requestBody=JSON.stringify({
    action,scenario:$("ai-scenario").value,language:$("speech-language").value,history
  });
  let response=await fetch("/api/gemini/reply/stream",{method:"POST",
    headers:{"Content-Type":"application/json"},body:requestBody
  });
  if(response.status===404||response.status===405){
    response=await fetch("/api/gemini/reply",{method:"POST",
      headers:{"Content-Type":"application/json"},body:requestBody
    });
    if(!response.ok){
      const error=await response.json().catch(()=>({}));
      throw new Error(error.detail||`Gemini request failed (${response.status})`);
    }
    const result=await response.json();
    if(typeof result.reply!=="string"||!result.reply.trim()){
      throw new Error("Gemini returned an empty reply. Please try again.");
    }
    onChunk(result.reply);
    return result.reply.trim();
  }
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw new Error(error.detail||`Gemini request failed (${response.status})`);
  }
  if(!response.body)throw new Error("Gemini did not return a streaming response.");
  const reader=response.body.getReader();
  const decoder=new TextDecoder();
  let buffer="",reply="",complete=false;
  const processLine=line=>{
    if(!line.startsWith("data:"))return;
    const event=JSON.parse(line.slice(5).trim());
    if(event.type==="chunk"){
      reply+=event.text;
      onChunk(event.text);
    }else if(event.type==="error"){
      throw new Error(event.message||"Gemini reply failed.");
    }else if(event.type==="done"){
      complete=true;
    }
  };
  while(!complete){
    const {value,done}=await reader.read();
    buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
    const lines=buffer.split("\n");
    buffer=lines.pop();
    for(const line of lines)processLine(line.replace(/\r$/,""));
    if(done){
      if(buffer)processLine(buffer.replace(/\r$/,""));
      break;
    }
  }
  if(!complete||!reply.trim())throw new Error("Gemini returned an incomplete reply. Please try again.");
  return reply.trim();
}
$("ai-start").addEventListener("click",async()=>{
  if(!geminiConfigured||!gnaniConfigured)return;
  aiActive=true;aiBusy=true;aiUserTurns=0;aiHistory=[];
  $("ai-thread").replaceChildren();$("ai-thread").classList.remove("hidden");
  $("ai-composer").classList.remove("hidden");$("ai-scenario").disabled=true;$("ai-start").hidden=true;
  const scenarioLabel=$("ai-scenario").selectedOptions[0].textContent;
  const opening=$("ai-scenario").value==="open-conversation"
    ?"Let's have a friendly everyday conversation."
    :`Let's practise a conversation about ${scenarioLabel}.`;
  aiHistory=[{role:"user",text:opening}];addAiMessage("user",opening);
  updateAiControls();notify("Connecting Gemini and Gnani…");
  let replyBubble=null;
  try{
    const reply=await requestGemini("start",[],text=>{
      if(!replyBubble)replyBubble=addAiMessage("model",text);
      else replyBubble.lastChild.textContent+=text;
    });
    if(!replyBubble)replyBubble=addAiMessage("model",reply);
    else replyBubble.lastChild.textContent=reply;
    aiHistory.push({role:"model",text:reply});
    void speakAiReply(reply);
  }catch(error){
    replyBubble?.remove();
    aiActive=false;aiHistory=[];$("ai-scenario").disabled=false;$("ai-start").hidden=false;
    notify(error.message);
  }finally{aiBusy=false;updateAiControls();}
});
$("ai-input").addEventListener("input",updateAiControls);
$("ai-send").addEventListener("click",async()=>{
  const text=$("ai-input").value.trim();
  if(!text||!aiActive||aiBusy)return;
  if(aiHistory.length+1>14){notify("This conversation reached its turn limit. End and save it, then start a new one.");return;}
  stopAiSpeech();
  const userMessage={role:"user",text};
  const nextHistory=[...aiHistory,userMessage];
  const bubble=addAiMessage("user",text);
  aiBusy=true;$("ai-input").value="";updateAiControls();
  let replyBubble=null;
  try{
    const reply=await requestGemini("reply",nextHistory,chunk=>{
      if(!replyBubble)replyBubble=addAiMessage("model",chunk);
      else replyBubble.lastChild.textContent+=chunk;
    });
    aiHistory=[...nextHistory,{role:"model",text:reply}];aiUserTurns++;
    if(!replyBubble)replyBubble=addAiMessage("model",reply);
    else replyBubble.lastChild.textContent=reply;
    void speakAiReply(reply);
  }catch(error){
    bubble.remove();replyBubble?.remove();$("ai-input").value=text;notify(error.message);
  }finally{aiBusy=false;updateAiControls();}
});
$("ai-save").addEventListener("click",async()=>{
  if(!aiActive||aiBusy||aiUserTurns===0)return;
  aiBusy=true;updateAiControls();
  try{
    await api("/api/gemini/save",{method:"POST",body:JSON.stringify({
      scenario:$("ai-scenario").value,history:aiHistory
    })});
    aiActive=false;$("ai-scenario").disabled=false;$("ai-start").hidden=false;
    $("ai-start").textContent="Start another conversation ↗";
    notify("Conversation saved to your practice history.");loadSessions();
  }catch(error){notify(error.message);}
  finally{aiBusy=false;updateAiControls();}
});
$("submit-practice").addEventListener("click",async()=>{
  if((!selected&&!selectedConversation)||!$("transcript").value.trim())return;
  if(selectedConversation){await saveConversationTurn();return;}
  const button=$("submit-practice");button.dataset.submitting="true";updateTranscriptState();button.textContent="Reviewing…";
  try{
    const data=await api("/api/practice/feedback",{method:"POST",body:JSON.stringify({exercise_id:selected.id,transcript:$("transcript").value})});
    const f=data.feedback;const box=$("feedback");box.replaceChildren();
    const title=document.createElement("strong");title.textContent=`Prompt word overlap: ${f.prompt_word_overlap_percent}%`;
    const msg=document.createElement("p");msg.textContent=f.message;
    const matched=document.createElement("p");matched.textContent="Matched words: "+(f.matched_words.join(", ")||"None");
    const missing=document.createElement("p");missing.textContent="Words to revisit: "+(f.missing_words.join(", ")||"None");
    const note=document.createElement("small");note.textContent=f.disclaimer;
    box.append(title,msg,matched,missing,note);box.classList.remove("hidden");notify("Practice session saved.");loadSessions();
  }catch(e){notify(e.message);}
  finally{delete button.dataset.submitting;button.innerHTML='Review practice <span>↗</span>';updateTranscriptState();}
});
async function saveConversationTurn(){
  const button=$("submit-practice");
  if(conversationState.completed)return;
  const transcript=$("transcript").value.trim();
  if(!transcript)return;
  conversationState.turns.push({turn_index:conversationState.index,transcript});
  $("feedback").classList.add("hidden");
  if(conversationState.index<selectedConversation.turns.length-1){
    conversationState.index++;
    $("transcript").value="";
    renderConversationTurn();updateTranscriptState();
    notify(`Turn ${conversationState.index} saved. Continue the conversation.`);
    return;
  }
  button.dataset.submitting="true";updateTranscriptState();button.textContent="Saving conversation…";
  try{
    const data=await api("/api/conversations/complete",{method:"POST",body:JSON.stringify({
      conversation_id:selectedConversation.id,turns:conversationState.turns
    })});
    conversationState.completed=true;
    const box=$("feedback");box.replaceChildren();
    const title=document.createElement("strong");title.textContent=`Role-play complete · ${data.feedback.completed_turns} turns`;
    const message=document.createElement("p");message.textContent=data.feedback.message;
    const note=document.createElement("small");note.textContent=data.feedback.disclaimer;
    box.append(title,message,note);box.classList.remove("hidden");
    notify("Conversation saved to your practice history.");loadSessions();
  }catch(e){
    conversationState.turns.pop();
    notify(e.message);
  }finally{
    delete button.dataset.submitting;updateTranscriptState();
  }
}
function renderSessions(sessions){
  $("session-count").textContent=sessions.length;
  const scores=sessions.filter(s=>s.feedback.activity_type!=="conversation")
    .map(s=>s.feedback.prompt_word_overlap_percent ?? s.feedback.word_coverage_percent).filter(Number.isFinite);
  $("avg-score").textContent=scores.length?Math.round(scores.reduce((a,b)=>a+b,0)/scores.length)+"%":"—";
  $("latest-date").textContent=sessions.length?new Date(sessions[0].created_at).toLocaleDateString(undefined,{month:"short",day:"numeric"}):"—";
  const list=$("session-list");list.replaceChildren();
  if(!sessions.length){const empty=document.createElement("div");empty.className="empty-state";empty.textContent="Your completed practice sessions will appear here. Choose an activity to get started.";list.append(empty);return;}
  sessions.forEach(s=>{const row=document.createElement("article");row.className="session";const left=document.createElement("div");const title=document.createElement("div");title.className="session-title";title.textContent=s.target;const date=document.createElement("p");date.textContent=new Date(s.created_at).toLocaleString();left.append(title,date);const score=document.createElement("span");score.className="session-score";score.textContent=s.feedback.activity_type==="ai_conversation"?`Gemini · ${s.feedback.completed_turns} turns`:s.feedback.activity_type==="conversation"?`Role-play · ${s.feedback.completed_turns} turns`:`${s.feedback.prompt_word_overlap_percent ?? s.feedback.word_coverage_percent}% overlap`;row.append(left,score);list.append(row);});
}
async function loadSessions(){try{const {sessions}=await api("/api/sessions");renderSessions(sessions);}catch(e){notify(e.message);}}
function setConnection(online){$("connection").classList.toggle("offline",!online);$("connection").textContent=online?"● Live sync":"● Reconnecting";}
function connectEvents(){
  if(!("EventSource" in window)){setConnection(false);$("sync-status").textContent="REFRESH TO SYNC";return;}
  if(eventSource)eventSource.close();eventSource=new EventSource("/api/events");
  eventSource.onopen=()=>{setConnection(true);$("sync-status").textContent="LIVE SYNC ON";};
  eventSource.onerror=()=>{setConnection(false);$("sync-status").textContent="RECONNECTING";};
  eventSource.addEventListener("session",e=>{try{const event=JSON.parse(e.data);if(!event.id||seenEvents.has(event.id))return;seenEvents.add(event.id);if(seenEvents.size>200)seenEvents.delete(seenEvents.values().next().value);if($("progress").classList.contains("active"))loadSessions();}catch(_){}});
}
window.addEventListener("beforeunload",()=>{if(eventSource)eventSource.close();stopLiveCapture(false);});
init();
