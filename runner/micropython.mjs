async function _createMicroPythonModule(moduleArg={}){var Module=moduleArg;var ENVIRONMENT_IS_WEB=!!globalThis.window;var ENVIRONMENT_IS_WORKER=!!globalThis.WorkerGlobalScope;var ENVIRONMENT_IS_NODE=globalThis.process?.versions?.node&&globalThis.process?.type!="renderer";if(ENVIRONMENT_IS_NODE){const{createRequire}=await import("node:module");var require=createRequire(import.meta.url)}var programArgs=[];var thisProgram="./this.program";var quit_=(status,toThrow)=>{throw toThrow};var _scriptName=import.meta.url;var scriptDirectory="";function locateFile(path){if(Module["locateFile"]){return Module["locateFile"](path,scriptDirectory)}return scriptDirectory+path}var readAsync,readBinary;if(ENVIRONMENT_IS_NODE){var fs=require("node:fs");if(_scriptName.startsWith("file:")){scriptDirectory=require("node:path").dirname(require("node:url").fileURLToPath(_scriptName))+"/"}readBinary=filename=>{filename=isFileURI(filename)?new URL(filename):filename;var ret=fs.readFileSync(filename);return ret};readAsync=async(filename,binary=true)=>{filename=isFileURI(filename)?new URL(filename):filename;var ret=fs.readFileSync(filename,binary?undefined:"utf8");return ret};if(process.argv.length>1){thisProgram=process.argv[1].replace(/\\/g,"/")}programArgs=process.argv.slice(2);quit_=(status,toThrow)=>{process.exitCode=status;throw toThrow}}else if(ENVIRONMENT_IS_WEB||ENVIRONMENT_IS_WORKER){try{scriptDirectory=new URL(".",_scriptName).href}catch{}{if(ENVIRONMENT_IS_WORKER){readBinary=url=>{var xhr=new XMLHttpRequest;xhr.open("GET",url,false);xhr.responseType="arraybuffer";xhr.send(null);return new Uint8Array(xhr.response)}}readAsync=async url=>{if(isFileURI(url)){return new Promise((resolve,reject)=>{var xhr=new XMLHttpRequest;xhr.open("GET",url,true);xhr.responseType="arraybuffer";xhr.onload=()=>{if(xhr.status==200||xhr.status==0&&xhr.response){resolve(xhr.response);return}reject(xhr.status)};xhr.onerror=reject;xhr.send(null)})}var response=await fetch(url,{credentials:"same-origin"});if(response.ok){return response.arrayBuffer()}throw new Error(response.status+" : "+response.url)}}}else{}var out=console.log.bind(console);var err=console.error.bind(console);var wasmBinary;var ABORT=false;var isFileURI=filename=>filename.startsWith("file://");class EmscriptenEH{}class EmscriptenSjLj extends EmscriptenEH{}var runtimeInitialized=false;function getMemoryBuffer(){return wasmMemory.buffer}function updateMemoryViews(){if(HEAP8?.buffer?.resizable)return;var b=getMemoryBuffer();HEAP8=new Int8Array(b);HEAP16=new Int16Array(b);HEAPU8=new Uint8Array(b);HEAP32=new Int32Array(b);HEAPU32=new Uint32Array(b);HEAPF32=new Float32Array(b);HEAPF64=new Float64Array(b);HEAP64=new BigInt64Array(b)}function preRun(){var preRun=Module["preRun"];if(preRun){if(typeof preRun=="function")preRun=[preRun];onPreRuns.push(...preRun)}callRuntimeCallbacks(onPreRuns)}function initRuntime(){runtimeInitialized=true;if(!Module["noFSInit"]&&!FS.initialized)FS.init();TTY.init();wasmExports["ka"]();FS.ignorePermissions=false}function postRun(){var postRun=Module["postRun"];if(postRun){if(typeof postRun=="function")postRun=[postRun];onPostRuns.push(...postRun)}callRuntimeCallbacks(onPostRuns)}function abort(what){Module["onAbort"]?.(what);what=`Aborted(${what})`;err(what);ABORT=true;what+=". Build with -sASSERTIONS for more info.";var e=new WebAssembly.RuntimeError(what);throw e}var wasmBinaryFile;function findWasmBinary(){if(Module["locateFile"]){return locateFile("micropython.wasm")}return new URL("micropython.wasm",import.meta.url).href}function getBinarySync(file){if(readBinary){return readBinary(file)}throw"both async and sync fetching of the wasm failed"}async function getWasmBinary(binaryFile){if(!wasmBinary){try{var response=await readAsync(binaryFile);return new Uint8Array(response)}catch{}}return getBinarySync(binaryFile)}async function instantiateArrayBuffer(binaryFile,imports){try{var binary=await getWasmBinary(binaryFile);var instance=await WebAssembly.instantiate(binary,imports);return instance}catch(reason){err(`failed to asynchronously prepare wasm: ${reason}`);abort(reason)}}async function instantiateAsync(binary,binaryFile,imports){if(!binary&&!isFileURI(binaryFile)&&!ENVIRONMENT_IS_NODE){try{var response=fetch(binaryFile,{credentials:"same-origin"});var instantiationResult=await WebAssembly.instantiateStreaming(response,imports);return instantiationResult}catch(reason){err(`wasm streaming compile failed: ${reason}`);err("falling back to ArrayBuffer instantiation")}}return instantiateArrayBuffer(binaryFile,imports)}function getWasmImports(){var imports={a:wasmImports};return imports}async function createWasm(){function receiveInstance(instance){wasmExports=instance.exports;assignWasmExports(wasmExports);updateMemoryViews();return wasmExports}function receiveInstantiationResult(result){return receiveInstance(result["instance"])}var info=getWasmImports();var instantiateWasm=Module["instantiateWasm"];if(instantiateWasm){return new Promise(resolve=>{instantiateWasm(info,inst=>resolve(receiveInstance(inst)))})}wasmBinaryFile??=findWasmBinary();var result=await instantiateAsync(wasmBinary,wasmBinaryFile,info);var exports=receiveInstantiationResult(result);return exports}class ExitStatus{name="ExitStatus";constructor(status){this.message=`Program terminated with exit(${status})`;this.status=status}}var HEAP8;var callRuntimeCallbacks=callbacks=>{while(callbacks.length>0){callbacks.shift()(Module)}};var onPostRuns=[];var onPreRuns=[];var noExitRuntime=true;var stackRestore=val=>__emscripten_stack_restore(val);var stackSave=()=>_emscripten_stack_get_current();var PATH={isAbs:path=>path.charAt(0)==="/",splitPath:filename=>{var splitPathRe=/^(\/?|)([\s\S]*?)((?:\.{1,2}|[^\/]+?|)(\.[^.\/]*|))(?:[\/]*)$/;return splitPathRe.exec(filename).slice(1)},normalizeArray:(parts,allowAboveRoot)=>{var up=0;for(var i=parts.length-1;i>=0;i--){var last=parts[i];if(last==="."){parts.splice(i,1)}else if(last===".."){parts.splice(i,1);up++}else if(up){parts.splice(i,1);up--}}if(allowAboveRoot){for(;up;up--){parts.unshift("..")}}return parts},normalize:path=>{var isAbsolute=PATH.isAbs(path),trailingSlash=path.slice(-1)==="/";path=PATH.normalizeArray(path.split("/").filter(p=>!!p),!isAbsolute).join("/");if(!path&&!isAbsolute){path="."}if(path&&trailingSlash){path+="/"}return(isAbsolute?"/":"")+path},dirname:path=>{var result=PATH.splitPath(path),root=result[0],dir=result[1];if(!root&&!dir){return"."}if(dir){dir=dir.slice(0,-1)}return root+dir},basename:path=>path&&path.match(/([^\/]+|\/)\/*$/)[1],join:(...paths)=>PATH.normalize(paths.join("/")),join2:(l,r)=>PATH.normalize(l+"/"+r)};var initRandomFill=()=>{if(ENVIRONMENT_IS_NODE){var nodeCrypto=require("node:crypto");return view=>(nodeCrypto.randomFillSync(view),0)}return view=>(crypto.getRandomValues(view),0)};var randomFill=view=>(randomFill=initRandomFill())(view);var PATH_FS={resolve:(...args)=>{var resolvedPath="",resolvedAbsolute=false;for(var i=args.length-1;i>=-1&&!resolvedAbsolute;i--){var path=i>=0?args[i]:FS.cwd();if(typeof path!="string"){throw new TypeError("Arguments to path.resolve must be strings")}else if(!path){return""}resolvedPath=path+"/"+resolvedPath;resolvedAbsolute=PATH.isAbs(path)}resolvedPath=PATH.normalizeArray(resolvedPath.split("/").filter(p=>!!p),!resolvedAbsolute).join("/");return(resolvedAbsolute?"/":"")+resolvedPath||"."},relative:(from,to)=>{from=PATH_FS.resolve(from).slice(1);to=PATH_FS.resolve(to).slice(1);function trim(arr){var start=0;for(;start<arr.length;start++){if(arr[start]!=="")break}var end=arr.length-1;for(;end>=0;end--){if(arr[end]!=="")break}if(start>end)return[];return arr.slice(start,end-start+1)}var fromParts=trim(from.split("/"));var toParts=trim(to.split("/"));var length=Math.min(fromParts.length,toParts.length);var samePartsLength=length;for(var i=0;i<length;i++){if(fromParts[i]!==toParts[i]){samePartsLength=i;break}}var outputParts=[];for(var i=samePartsLength;i<fromParts.length;i++){outputParts.push("..")}outputParts=outputParts.concat(toParts.slice(samePartsLength));return outputParts.join("/")}};var UTF8Decoder=globalThis.TextDecoder&&new TextDecoder;var findStringEnd=(heapOrArray,idx,maxBytesToRead,ignoreNul)=>{var maxIdx=idx+maxBytesToRead;if(ignoreNul)return maxIdx;while(heapOrArray[idx]&&!(idx>=maxIdx))++idx;return idx};var UTF8ArrayToString=(heapOrArray,idx=0,maxBytesToRead,ignoreNul)=>{var endPtr=findStringEnd(heapOrArray,idx,maxBytesToRead,ignoreNul);if(endPtr-idx>16&&heapOrArray.buffer&&UTF8Decoder){return UTF8Decoder.decode(heapOrArray.subarray(idx,endPtr))}var str="";while(idx<endPtr){var u0=heapOrArray[idx++];if(!(u0&128)){str+=String.fromCharCode(u0);continue}var u1=heapOrArray[idx++]&63;if((u0&224)==192){str+=String.fromCharCode((u0&31)<<6|u1);continue}var u2=heapOrArray[idx++]&63;if((u0&240)==224){u0=(u0&15)<<12|u1<<6|u2}else{u0=(u0&7)<<18|u1<<12|u2<<6|heapOrArray[idx++]&63}if(u0<65536){str+=String.fromCharCode(u0)}else{var ch=u0-65536;str+=String.fromCharCode(55296|ch>>10,56320|ch&1023)}}return str};var FS_stdin_getChar_buffer=[];var lengthBytesUTF8=str=>{var len=0;for(var i=0;i<str.length;++i){var c=str.charCodeAt(i);if(c<=127){len++}else if(c<=2047){len+=2}else if(c>=55296&&c<=57343){len+=4;++i}else{len+=3}}return len};var stringToUTF8Array=(str,heap,outIdx,maxBytesToWrite)=>{if(!(maxBytesToWrite>0))return 0;var startIdx=outIdx;var endIdx=outIdx+maxBytesToWrite-1;for(var i=0;i<str.length;++i){var u=str.codePointAt(i);if(u<=127){if(outIdx>=endIdx)break;heap[outIdx++]=u}else if(u<=2047){if(outIdx+1>=endIdx)break;heap[outIdx++]=192|u>>6;heap[outIdx++]=128|u&63}else if(u<=65535){if(outIdx+2>=endIdx)break;heap[outIdx++]=224|u>>12;heap[outIdx++]=128|u>>6&63;heap[outIdx++]=128|u&63}else{if(outIdx+3>=endIdx)break;heap[outIdx++]=240|u>>18;heap[outIdx++]=128|u>>12&63;heap[outIdx++]=128|u>>6&63;heap[outIdx++]=128|u&63;i++}}heap[outIdx]=0;return outIdx-startIdx};var intArrayFromString=(stringy,dontAddNull,length)=>{var len=length>0?length:lengthBytesUTF8(stringy)+1;var u8array=new Array(len);var numBytesWritten=stringToUTF8Array(stringy,u8array,0,u8array.length);if(dontAddNull)u8array.length=numBytesWritten;return u8array};var FS_stdin_getChar=()=>{if(!FS_stdin_getChar_buffer.length){var result=null;if(ENVIRONMENT_IS_NODE){var BUFSIZE=256;var buf=Buffer.alloc(BUFSIZE);var bytesRead=0;var fd=process.stdin.fd;try{bytesRead=fs.readSync(fd,buf,0,BUFSIZE)}catch(e){if(e.toString().includes("EOF"))bytesRead=0;else throw e}if(bytesRead>0){result=buf.slice(0,bytesRead).toString("utf-8")}}else if(globalThis.window?.prompt){result=window.prompt("Input: ");if(result!==null){result+="\n"}}else{}if(!result){return null}FS_stdin_getChar_buffer=intArrayFromString(result,true)}return FS_stdin_getChar_buffer.shift()};var TTY={ttys:[],init(){},shutdown(){},register(dev,ops){TTY.ttys[dev]={input:[],output:[],ops};FS.registerDevice(dev,TTY.stream_ops)},stream_ops:{open(stream){var tty=TTY.ttys[stream.node.rdev];if(!tty){throw new FS.ErrnoError(43)}stream.tty=tty;stream.seekable=false},close(stream){stream.tty.ops.fsync(stream.tty)},fsync(stream){stream.tty.ops.fsync(stream.tty)},read(stream,buffer,offset,length,pos){if(!stream.tty||!stream.tty.ops.get_char){throw new FS.ErrnoError(60)}var bytesRead=0;for(var i=0;i<length;i++){var result;try{result=stream.tty.ops.get_char(stream.tty)}catch(e){throw new FS.ErrnoError(29)}if(result===undefined&&bytesRead===0){throw new FS.ErrnoError(6)}if(result===null||result===undefined)break;bytesRead++;buffer[offset+i]=result}if(bytesRead){stream.node.atime=Date.now()}return bytesRead},write(stream,buffer,offset,length,pos){if(!stream.tty||!stream.tty.ops.put_char){throw new FS.ErrnoError(60)}try{for(var i=0;i<length;i++){stream.tty.ops.put_char(stream.tty,buffer[offset+i])}}catch(e){throw new FS.ErrnoError(29)}if(length){stream.node.mtime=stream.node.ctime=Date.now()}return i}},default_tty_ops:{get_char(tty){return FS_stdin_getChar()},put_char(tty,val){if(val===null||val===10){out(UTF8ArrayToString(tty.output));tty.output=[]}else{if(val!=0)tty.output.push(val)}},fsync(tty){if(tty.output?.length>0){out(UTF8ArrayToString(tty.output));tty.output=[]}},ioctl_tcgets(tty){return{c_iflag:25856,c_oflag:5,c_cflag:191,c_lflag:35387,c_cc:[3,28,127,21,4,0,1,0,17,19,26,0,18,15,23,22,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}},ioctl_tcsets(tty,optional_actions,data){return 0},ioctl_tiocgwinsz(tty){return[24,80]}},default_tty1_ops:{put_char(tty,val){if(val===null||val===10){err(UTF8ArrayToString(tty.output));tty.output=[]}else{if(val!=0)tty.output.push(val)}},fsync(tty){if(tty.output?.length>0){err(UTF8ArrayToString(tty.output));tty.output=[]}}}};var mmapAlloc=size=>{abort()};var MEMFS={ops_table:null,mount(mount){return MEMFS.createNode(null,"/",16895,0)},createNode(parent,name,mode,dev){if(FS.isBlkdev(mode)||FS.isFIFO(mode)){throw new FS.ErrnoError(63)}MEMFS.ops_table||={dir:{node:{getattr:MEMFS.node_ops.getattr,setattr:MEMFS.node_ops.setattr,lookup:MEMFS.node_ops.lookup,mknod:MEMFS.node_ops.mknod,rename:MEMFS.node_ops.rename,unlink:MEMFS.node_ops.unlink,rmdir:MEMFS.node_ops.rmdir,readdir:MEMFS.node_ops.readdir,symlink:MEMFS.node_ops.symlink},stream:{llseek:MEMFS.stream_ops.llseek}},file:{node:{getattr:MEMFS.node_ops.getattr,setattr:MEMFS.node_ops.setattr},stream:{llseek:MEMFS.stream_ops.llseek,read:MEMFS.stream_ops.read,write:MEMFS.stream_ops.write,mmap:MEMFS.stream_ops.mmap,msync:MEMFS.stream_ops.msync}},link:{node:{getattr:MEMFS.node_ops.getattr,setattr:MEMFS.node_ops.setattr,readlink:MEMFS.node_ops.readlink},stream:{}},chrdev:{node:{getattr:MEMFS.node_ops.getattr,setattr:MEMFS.node_ops.setattr},stream:FS.chrdev_stream_ops}};var node=FS.createNode(parent,name,mode,dev);if(FS.isDir(node.mode)){node.node_ops=MEMFS.ops_table.dir.node;node.stream_ops=MEMFS.ops_table.dir.stream;node.contents={}}else if(FS.isFile(node.mode)){node.node_ops=MEMFS.ops_table.file.node;node.stream_ops=MEMFS.ops_table.file.stream;node.usedBytes=0;node.contents=MEMFS.emptyFileContents??=new Uint8Array(0)}else if(FS.isLink(node.mode)){node.node_ops=MEMFS.ops_table.link.node;node.stream_ops=MEMFS.ops_table.link.stream}else if(FS.isChrdev(node.mode)){node.node_ops=MEMFS.ops_table.chrdev.node;node.stream_ops=MEMFS.ops_table.chrdev.stream}node.atime=node.mtime=node.ctime=Date.now();if(parent){parent.contents[name]=node;parent.atime=parent.mtime=parent.ctime=node.atime}return node},getFileDataAsTypedArray(node){return node.contents.subarray(0,node.usedBytes)},expandFileStorage(node,newCapacity){var prevCapacity=node.contents.length;if(prevCapacity>=newCapacity)return;var CAPACITY_DOUBLING_MAX=1024*1024;newCapacity=Math.max(newCapacity,prevCapacity*(prevCapacity<CAPACITY_DOUBLING_MAX?2:1.125)>>>0);if(prevCapacity)newCapacity=Math.max(newCapacity,256);var oldContents=MEMFS.getFileDataAsTypedArray(node);node.contents=new Uint8Array(newCapacity);node.contents.set(oldContents)},resizeFileStorage(node,newSize){if(node.usedBytes==newSize)return;var oldContents=node.contents;node.contents=new Uint8Array(newSize);node.contents.set(oldContents.subarray(0,Math.min(newSize,node.usedBytes)));node.usedBytes=newSize},node_ops:{getattr(node){var attr={};attr.dev=FS.isChrdev(node.mode)?node.id:1;attr.ino=node.id;attr.mode=node.mode;attr.nlink=1;attr.uid=0;attr.gid=0;attr.rdev=node.rdev;if(FS.isDir(node.mode)){attr.size=4096}else if(FS.isFile(node.mode)){attr.size=node.usedBytes}else if(FS.isLink(node.mode)){attr.size=node.link.length}else{attr.size=0}attr.atime=new Date(node.atime);attr.mtime=new Date(node.mtime);attr.ctime=new Date(node.ctime);attr.blksize=4096;attr.blocks=Math.ceil(attr.size/attr.blksize);return attr},setattr(node,attr){for(const key of["mode","atime","mtime","ctime"]){if(attr[key]!=null){node[key]=attr[key]}}if(attr.size!==undefined){MEMFS.resizeFileStorage(node,attr.size)}},lookup(parent,name){if(!MEMFS.doesNotExistError){MEMFS.doesNotExistError=new FS.ErrnoError(44);MEMFS.doesNotExistError.stack="<generic error, no stack>"}throw MEMFS.doesNotExistError},mknod(parent,name,mode,dev){return MEMFS.createNode(parent,name,mode,dev)},rename(old_node,new_dir,new_name){var new_node;try{new_node=FS.lookupNode(new_dir,new_name)}catch(e){}if(new_node){if(FS.isDir(old_node.mode)){for(var i in new_node.contents){throw new FS.ErrnoError(55)}}FS.hashRemoveNode(new_node)}delete old_node.parent.contents[old_node.name];new_dir.contents[new_name]=old_node;old_node.name=new_name;new_dir.ctime=new_dir.mtime=old_node.parent.ctime=old_node.parent.mtime=Date.now()},unlink(parent,name){delete parent.contents[name];parent.ctime=parent.mtime=Date.now()},rmdir(parent,name){var node=FS.lookupNode(parent,name);for(var i in node.contents){throw new FS.ErrnoError(55)}delete parent.contents[name];parent.ctime=parent.mtime=Date.now()},readdir(node){return[".","..",...Object.keys(node.contents)]},symlink(parent,newname,oldpath){var node=MEMFS.createNode(parent,newname,511|40960,0);node.link=oldpath;return node},readlink(node){if(!FS.isLink(node.mode)){throw new FS.ErrnoError(28)}return node.link}},stream_ops:{read(stream,buffer,offset,length,position){var contents=stream.node.contents;if(position>=stream.node.usedBytes)return 0;var size=Math.min(stream.node.usedBytes-position,length);buffer.set(contents.subarray(position,position+size),offset);return size},write(stream,buffer,offset,length,position,canOwn){if(buffer.buffer===HEAP8.buffer){canOwn=false}if(!length)return 0;var node=stream.node;node.mtime=node.ctime=Date.now();if(canOwn){node.contents=buffer.subarray(offset,offset+length);node.usedBytes=length}else if(node.usedBytes===0&&position===0){node.contents=buffer.slice(offset,offset+length);node.usedBytes=length}else{MEMFS.expandFileStorage(node,position+length);node.contents.set(buffer.subarray(offset,offset+length),position);node.usedBytes=Math.max(node.usedBytes,position+length)}return length},llseek(stream,offset,whence){var position=offset;if(whence===1){position+=stream.position}else if(whence===2){if(FS.isFile(stream.node.mode)){position+=stream.node.usedBytes}}if(position<0){throw new FS.ErrnoError(28)}return position},mmap(stream,length,position,prot,flags){if(!FS.isFile(stream.node.mode)){throw new FS.ErrnoError(43)}var ptr;var allocated;var contents=stream.node.contents;if(!(flags&2)&&contents.buffer===HEAP8.buffer){allocated=false;ptr=contents.byteOffset}else{allocated=true;ptr=mmapAlloc(length);if(!ptr){throw new FS.ErrnoError(48)}if(contents){if(position>0||position+length<contents.length){if(contents.subarray){contents=contents.subarray(position,position+length)}else{contents=Array.prototype.slice.call(contents,position,position+length)}}HEAP8.set(contents,ptr)}}return{ptr,allocated}},msync(stream,buffer,offset,length,mmapFlags){MEMFS.stream_ops.write(stream,buffer,0,length,offset,false);return 0}}};var FS_modeStringToFlags=str=>{if(typeof str!="string")return str;var flagModes={r:0,"r+":2,w:512|64|1,"w+":512|64|2,a:1024|64|1,"a+":1024|64|2};var flags=flagModes[str];if(typeof flags=="undefined"){throw new Error(`Unknown file open mode: ${str}`)}return flags};var FS_fileDataToTypedArray=data=>{if(typeof data=="string"){data=intArrayFromString(data,true)}if(!data.subarray){data=new Uint8Array(data)}return data};var FS_getMode=(canRead,canWrite)=>{var mode=0;if(canRead)mode|=292|73;if(canWrite)mode|=146;return mode};var asyncLoad=async url=>{var arrayBuffer=await readAsync(url);return new Uint8Array(arrayBuffer)};var FS_createDataFile=(...args)=>FS.createDataFile(...args);var getUniqueRunDependency=id=>id;var dependenciesPromise=null;var resolveRunDependencies=async()=>dependenciesPromise;var runDependencies=0;var dependenciesPromiseResolve=null;var removeRunDependency=id=>{runDependencies--;Module["monitorRunDependencies"]?.(runDependencies);if(!runDependencies){dependenciesPromiseResolve()}};var addRunDependency=id=>{if(!runDependencies){dependenciesPromise=new Promise(resolve=>dependenciesPromiseResolve=resolve)}runDependencies++;Module["monitorRunDependencies"]?.(runDependencies)};var preloadPlugins=[];var FS_handledByPreloadPlugin=async(byteArray,fullname)=>{if(typeof Browser!="undefined")Browser.init();for(var plugin of preloadPlugins){if(plugin["canHandle"](fullname)){return plugin["handle"](byteArray,fullname)}}return byteArray};var FS_preloadFile=async(parent,name,url,canRead,canWrite,dontCreateFile,canOwn,preFinish)=>{var fullname=name?PATH_FS.resolve(PATH.join2(parent,name)):parent;var dep=getUniqueRunDependency(`cp ${fullname}`);addRunDependency(dep);try{var byteArray=url;if(typeof url=="string"){byteArray=await asyncLoad(url)}byteArray=await FS_handledByPreloadPlugin(byteArray,fullname);preFinish?.();if(!dontCreateFile){FS_createDataFile(parent,name,byteArray,canRead,canWrite,canOwn)}}finally{removeRunDependency(dep)}};var FS_createPreloadedFile=(parent,name,url,canRead,canWrite,onload,onerror,dontCreateFile,canOwn,preFinish)=>{FS_preloadFile(parent,name,url,canRead,canWrite,dontCreateFile,canOwn,preFinish).then(onload).catch(onerror)};var FS={root:null,mounts:[],devices:{},streams:[],nextInode:1,nameTable:null,currentPath:"/",initialized:false,ignorePermissions:true,filesystems:null,syncFSRequests:0,ErrnoError:class{name="ErrnoError";constructor(errno){this.errno=errno}},FSStream:class{shared={};get object(){return this.node}set object(val){this.node=val}get isRead(){return(this.flags&2097155)!==1}get isWrite(){return(this.flags&2097155)!==0}get isAppend(){return this.flags&1024}get flags(){return this.shared.flags}set flags(val){this.shared.flags=val}get position(){return this.shared.position}set position(val){this.shared.position=val}},FSNode:class{node_ops={};stream_ops={};readMode=292|73;writeMode=146;mounted=null;constructor(parent,name,mode,rdev){if(!parent){parent=this}this.parent=parent;this.mount=parent.mount;this.id=FS.nextInode++;this.name=name;this.mode=mode;this.rdev=rdev;this.atime=this.mtime=this.ctime=Date.now()}get read(){return(this.mode&this.readMode)===this.readMode}set read(val){val?this.mode|=this.readMode:this.mode&=~this.readMode}get write(){return(this.mode&this.writeMode)===this.writeMode}set write(val){val?this.mode|=this.writeMode:this.mode&=~this.writeMode}get isFolder(){return FS.isDir(this.mode)}get isDevice(){return FS.isChrdev(this.mode)}addListener(cb,exclusive=false){var entry={cb,exclusive};var listeners=this.listeners??=new Set;listeners.add(entry);return{listeners,entry}}notifyListeners(flags){if(!this.listeners)return;var excl;for(var entry of this.listeners){if(entry.exclusive)(excl||=[]).push(entry);else entry.cb(flags)}if(excl){var i=(this.exclTurn||0)%excl.length;this.exclTurn=i+1;excl[i].cb(flags)}}},lookupPath(path,opts={}){if(!path){throw new FS.ErrnoError(44)}opts.follow_mount??=true;if(!PATH.isAbs(path)){path=FS.cwd()+"/"+path}linkloop:for(var nlinks=0;nlinks<40;nlinks++){var parts=path.split("/").filter(p=>!!p);var current=FS.root;var current_path="/";for(var i=0;i<parts.length;i++){var islast=i===parts.length-1;if(islast&&opts.parent){break}if(parts[i]==="."){continue}if(parts[i]===".."){current_path=PATH.dirname(current_path);if(FS.isRoot(current)){path=current_path+"/"+parts.slice(i+1).join("/");nlinks--;continue linkloop}else{current=current.parent}continue}current_path=PATH.join2(current_path,parts[i]);try{current=FS.lookupNode(current,parts[i])}catch(e){if(e?.errno===44&&islast&&opts.noent_okay){return{path:current_path}}throw e}if(FS.isMountpoint(current)&&(!islast||opts.follow_mount)){current=current.mounted.root}if(FS.isLink(current.mode)&&(!islast||opts.follow)){if(!current.node_ops.readlink){throw new FS.ErrnoError(52)}var link=current.node_ops.readlink(current);if(!PATH.isAbs(link)){link=PATH.dirname(current_path)+"/"+link}path=link+"/"+parts.slice(i+1).join("/");continue linkloop}}return{path:current_path,node:current}}throw new FS.ErrnoError(32)},getPath(node){var path;while(true){if(FS.isRoot(node)){var mount=node.mount.mountpoint;if(!path)return mount;return mount[mount.length-1]!=="/"?`${mount}/${path}`:mount+path}path=path?`${node.name}/${path}`:node.name;node=node.parent}},hashName(parentid,name){var hash=0;for(var i=0;i<name.length;i++){hash=(hash<<5)-hash+name.charCodeAt(i)|0}return(parentid+hash>>>0)%FS.nameTable.length},hashAddNode(node){var hash=FS.hashName(node.parent.id,node.name);node.name_next=FS.nameTable[hash];FS.nameTable[hash]=node},hashRemoveNode(node){var hash=FS.hashName(node.parent.id,node.name);if(FS.nameTable[hash]===node){FS.nameTable[hash]=node.name_next}else{var current=FS.nameTable[hash];while(current){if(current.name_next===node){current.name_next=node.name_next;break}current=current.name_next}}},lookupNode(parent,name){var errCode=FS.mayLookup(parent);if(errCode){throw new FS.ErrnoError(errCode)}var hash=FS.hashName(parent.id,name);for(var node=FS.nameTable[hash];node;node=node.name_next){var nodeName=node.name;if(node.parent.id===parent.id&&nodeName===name){return node}}return FS.lookup(parent,name)},createNode(parent,name,mode,rdev){var node=new FS.FSNode(parent,name,mode,rdev);FS.hashAddNode(node);return node},destroyNode(node){FS.hashRemoveNode(node)},isRoot(node){return node===node.parent},isMountpoint(node){return!!node.mounted},isFile(mode){return(mode&61440)===32768},isDir(mode){return(mode&61440)===16384},isLink(mode){return(mode&61440)===40960},isChrdev(mode){return(mode&61440)===8192},isBlkdev(mode){return(mode&61440)===24576},isFIFO(mode){return(mode&61440)===4096},isSocket(mode){return(mode&49152)===49152},flagsToPermissionString(flag){var perms=["r","w","rw"][flag&3];if(flag&512){perms+="w"}return perms},nodePermissions(node,perms){if(FS.ignorePermissions){return 0}if(perms.includes("r")&&!(node.mode&292)){return 2}if(perms.includes("w")&&!(node.mode&146)){return 2}if(perms.includes("x")&&!(node.mode&73)){return 2}return 0},mayLookup(dir){if(!FS.isDir(dir.mode))return 54;var errCode=FS.nodePermissions(dir,"x");if(errCode)return errCode;if(!dir.node_ops.lookup)return 2;return 0},mayCreate(dir,name){if(!FS.isDir(dir.mode)){return 54}try{var node=FS.lookupNode(dir,name);return 20}catch(e){}return FS.nodePermissions(dir,"wx")},mayDelete(dir,name,isdir){var node;try{node=FS.lookupNode(dir,name)}catch(e){return e.errno}var errCode=FS.nodePermissions(dir,"wx");if(errCode){return errCode}if(isdir){if(!FS.isDir(node.mode)){return 54}if(FS.isRoot(node)||FS.getPath(node)===FS.cwd()){return 10}}else if(FS.isDir(node.mode)){return 31}return 0},mayOpen(node,flags){if(!node){return 44}if(FS.isLink(node.mode)){return 32}var mode=FS.flagsToPermissionString(flags);if(FS.isDir(node.mode)){if(mode!=="r"||flags&(512|64)){return 31}}return FS.nodePermissions(node,mode)},checkOpExists(op,err){if(!op){throw new FS.ErrnoError(err)}return op},MAX_OPEN_FDS:4096,nextfd(){for(var fd=0;fd<=FS.MAX_OPEN_FDS;fd++){if(!FS.streams[fd]){return fd}}throw new FS.ErrnoError(33)},getStreamChecked(fd){var stream=FS.getStream(fd);if(!stream){throw new FS.ErrnoError(8)}return stream},getStream:fd=>FS.streams[fd],createStream(stream,fd=-1){stream=Object.assign(new FS.FSStream,stream);if(fd==-1){fd=FS.nextfd()}stream.fd=fd;FS.streams[fd]=stream;return stream},closeStream(fd){FS.streams[fd]=null},dupStream(origStream,fd=-1){var stream=FS.createStream(origStream,fd);stream.stream_ops?.dup?.(stream);return stream},doSetAttr(stream,node,attr){var setattr=stream?.stream_ops.setattr;var arg=setattr?stream:node;setattr??=node.node_ops.setattr;FS.checkOpExists(setattr,63);try{setattr(arg,attr)}catch(e){if(e instanceof RangeError){throw new FS.ErrnoError(22)}throw e}},chrdev_stream_ops:{open(stream){var device=FS.getDevice(stream.node.rdev);stream.stream_ops=device.stream_ops;stream.stream_ops.open?.(stream)},llseek(){throw new FS.ErrnoError(70)}},major:dev=>dev>>8,minor:dev=>dev&255,makedev:(ma,mi)=>ma<<8|mi,registerDevice(dev,ops){FS.devices[dev]={stream_ops:ops}},getDevice:dev=>FS.devices[dev],getMounts(mount){var mounts=[];var check=[mount];while(check.length){var m=check.pop();mounts.push(m);check.push(...m.mounts)}return mounts},syncfs(populate,callback){if(typeof populate=="function"){callback=populate;populate=false}FS.syncFSRequests++;if(FS.syncFSRequests>1){err(`warning: ${FS.syncFSRequests} FS.syncfs operations in flight at once, probably just doing extra work`)}var mounts=FS.getMounts(FS.root.mount);var completed=0;function doCallback(errCode){FS.syncFSRequests--;return callback(errCode)}function done(errCode){if(errCode){if(!done.errored){done.errored=true;return doCallback(errCode)}return}if(++completed>=mounts.length){doCallback(null)}}for(var mount of mounts){if(mount.type.syncfs){mount.type.syncfs(mount,populate,done)}else{done(null)}}},mount(type,opts,mountpoint){var root=mountpoint==="/";var pseudo=!mountpoint;var node;if(root&&FS.root){throw new FS.ErrnoError(10)}else if(!root&&!pseudo){var lookup=FS.lookupPath(mountpoint,{follow_mount:false});mountpoint=lookup.path;node=lookup.node;if(FS.isMountpoint(node)){throw new FS.ErrnoError(10)}if(!FS.isDir(node.mode)){throw new FS.ErrnoError(54)}}var mount={type,opts,mountpoint,mounts:[]};var mountRoot=type.mount(mount);mountRoot.mount=mount;mount.root=mountRoot;if(root){FS.root=mountRoot}else if(node){node.mounted=mount;if(node.mount){node.mount.mounts.push(mount)}}return mountRoot},unmount(mountpoint){var lookup=FS.lookupPath(mountpoint,{follow_mount:false});if(!FS.isMountpoint(lookup.node)){throw new FS.ErrnoError(28)}var node=lookup.node;var mount=node.mounted;var mounts=FS.getMounts(mount);for(var[hash,current]of Object.entries(FS.nameTable)){while(current){var next=current.name_next;if(mounts.includes(current.mount)){FS.destroyNode(current)}current=next}}node.mounted=null;var idx=node.mount.mounts.indexOf(mount);node.mount.mounts.splice(idx,1)},lookup(parent,name){return parent.node_ops.lookup(parent,name)},mknod(path,mode,dev){var lookup=FS.lookupPath(path,{parent:true});var parent=lookup.node;var name=PATH.basename(path);if(!name){throw new FS.ErrnoError(28)}if(name==="."||name===".."){throw new FS.ErrnoError(20)}var errCode=FS.mayCreate(parent,name);if(errCode){throw new FS.ErrnoError(errCode)}if(!parent.node_ops.mknod){throw new FS.ErrnoError(63)}return parent.node_ops.mknod(parent,name,mode,dev)},statfs(path){return FS.statfsNode(FS.lookupPath(path,{follow:true}).node)},statfsStream(stream){return FS.statfsNode(stream.node)},statfsNode(node){var rtn={bsize:4096,frsize:4096,blocks:1e6,bfree:5e5,bavail:5e5,files:FS.nextInode,ffree:FS.nextInode-1,fsid:42,flags:2,namelen:255};if(node.node_ops.statfs){Object.assign(rtn,node.node_ops.statfs(node.mount.opts.root))}return rtn},create(path,mode=438){mode&=4095;mode|=32768;return FS.mknod(path,mode,0)},mkdir(path,mode=511){mode&=511|512;mode|=16384;return FS.mknod(path,mode,0)},mkdirTree(path,mode){var dirs=path.split("/");var d="";for(var dir of dirs){if(!dir)continue;if(d||PATH.isAbs(path))d+="/";d+=dir;try{FS.mkdir(d,mode)}catch(e){if(e.errno!=20)throw e}}},mkdev(path,mode,dev){if(typeof dev=="undefined"){dev=mode;mode=438}mode|=8192;return FS.mknod(path,mode,dev)},symlink(oldpath,newpath){if(!PATH_FS.resolve(oldpath)){throw new FS.ErrnoError(44)}var lookup=FS.lookupPath(newpath,{parent:true});var parent=lookup.node;if(!parent){throw new FS.ErrnoError(44)}var newname=PATH.basename(newpath);var errCode=FS.mayCreate(parent,newname);if(errCode){throw new FS.ErrnoError(errCode)}if(!parent.node_ops.symlink){throw new FS.ErrnoError(63)}return parent.node_ops.symlink(parent,newname,oldpath)},link(oldpath,newpath,flags){var lookup=FS.lookupPath(newpath,{parent:true});var parent=lookup.node;if(!parent){throw new FS.ErrnoError(44)}var newname=PATH.basename(newpath);var errCode=FS.mayCreate(parent,newname);if(errCode){throw new FS.ErrnoError(errCode)}if(!parent.node_ops.link){throw new FS.ErrnoError(34)}return parent.node_ops.link(parent,newname,oldpath,flags)},rename(old_path,new_path){var old_dirname=PATH.dirname(old_path);var new_dirname=PATH.dirname(new_path);var old_name=PATH.basename(old_path);var new_name=PATH.basename(new_path);var lookup,old_dir,new_dir;lookup=FS.lookupPath(old_path,{parent:true});old_dir=lookup.node;lookup=FS.lookupPath(new_path,{parent:true});new_dir=lookup.node;if(!old_dir||!new_dir)throw new FS.ErrnoError(44);if(old_dir.mount!==new_dir.mount){throw new FS.ErrnoError(75)}var old_node=FS.lookupNode(old_dir,old_name);var relative=PATH_FS.relative(old_path,new_dirname);if(relative.charAt(0)!=="."){throw new FS.ErrnoError(28)}relative=PATH_FS.relative(new_path,old_dirname);if(relative.charAt(0)!=="."){throw new FS.ErrnoError(55)}var new_node;try{new_node=FS.lookupNode(new_dir,new_name)}catch(e){}if(old_node===new_node){return}var isdir=FS.isDir(old_node.mode);var errCode=FS.mayDelete(old_dir,old_name,isdir);if(errCode){throw new FS.ErrnoError(errCode)}errCode=new_node?FS.mayDelete(new_dir,new_name,isdir):FS.mayCreate(new_dir,new_name);if(errCode){throw new FS.ErrnoError(errCode)}if(!old_dir.node_ops.rename){throw new FS.ErrnoError(63)}if(FS.isMountpoint(old_node)||new_node&&FS.isMountpoint(new_node)){throw new FS.ErrnoError(10)}if(new_dir!==old_dir){errCode=FS.nodePermissions(old_dir,"w");if(errCode){throw new FS.ErrnoError(errCode)}}FS.hashRemoveNode(old_node);try{old_dir.node_ops.rename(old_node,new_dir,new_name);old_node.parent=new_dir}catch(e){throw e}finally{FS.hashAddNode(old_node)}},rmdir(path){var lookup=FS.lookupPath(path,{parent:true});var parent=lookup.node;var name=PATH.basename(path);var node=FS.lookupNode(parent,name);var errCode=FS.mayDelete(parent,name,true);if(errCode){throw new FS.ErrnoError(errCode)}if(!parent.node_ops.rmdir){throw new FS.ErrnoError(63)}if(FS.isMountpoint(node)){throw new FS.ErrnoError(10)}parent.node_ops.rmdir(parent,name);FS.destroyNode(node)},readdir(path){var lookup=FS.lookupPath(path,{follow:true});var node=lookup.node;var readdir=FS.checkOpExists(node.node_ops.readdir,54);return readdir(node)},unlink(path){var lookup=FS.lookupPath(path,{parent:true});var parent=lookup.node;if(!parent){throw new FS.ErrnoError(44)}var name=PATH.basename(path);var node=FS.lookupNode(parent,name);var errCode=FS.mayDelete(parent,name,false);if(errCode){throw new FS.ErrnoError(errCode)}if(!parent.node_ops.unlink){throw new FS.ErrnoError(63)}if(FS.isMountpoint(node)){throw new FS.ErrnoError(10)}parent.node_ops.unlink(parent,name);FS.destroyNode(node)},readlink(path){var lookup=FS.lookupPath(path);var link=lookup.node;if(!link){throw new FS.ErrnoError(44)}if(!link.node_ops.readlink){throw new FS.ErrnoError(28)}return link.node_ops.readlink(link)},stat(path,dontFollow){var lookup=FS.lookupPath(path,{follow:!dontFollow});var node=lookup.node;var getattr=FS.checkOpExists(node.node_ops.getattr,63);return getattr(node)},fstat(fd){var stream=FS.getStreamChecked(fd);var node=stream.node;var getattr=stream.stream_ops.getattr;var arg=getattr?stream:node;getattr??=node.node_ops.getattr;FS.checkOpExists(getattr,63);return getattr(arg)},lstat(path){return FS.stat(path,true)},doChmod(stream,node,mode,dontFollow){FS.doSetAttr(stream,node,{mode:mode&4095|node.mode&~4095,ctime:Date.now(),dontFollow})},chmod(path,mode,dontFollow){var node;if(typeof path=="string"){var lookup=FS.lookupPath(path,{follow:!dontFollow});node=lookup.node}else{node=path}FS.doChmod(null,node,mode,dontFollow)},lchmod(path,mode){FS.chmod(path,mode,true)},fchmod(fd,mode){var stream=FS.getStreamChecked(fd);FS.doChmod(stream,stream.node,mode,false)},doChown(stream,node,dontFollow){FS.doSetAttr(stream,node,{timestamp:Date.now(),dontFollow})},chown(path,uid,gid,dontFollow){var node;if(typeof path=="string"){var lookup=FS.lookupPath(path,{follow:!dontFollow});node=lookup.node}else{node=path}FS.doChown(null,node,dontFollow)},lchown(path,uid,gid){FS.chown(path,uid,gid,true)},fchown(fd,uid,gid){var stream=FS.getStreamChecked(fd);FS.doChown(stream,stream.node,false)},doTruncate(stream,node,len){if(FS.isDir(node.mode)){throw new FS.ErrnoError(31)}if(!FS.isFile(node.mode)){throw new FS.ErrnoError(28)}var errCode=FS.nodePermissions(node,"w");if(errCode){throw new FS.ErrnoError(errCode)}FS.doSetAttr(stream,node,{size:len,timestamp:Date.now()})},truncate(path,len){if(len<0){throw new FS.ErrnoError(28)}var node;if(typeof path=="string"){var lookup=FS.lookupPath(path,{follow:true});node=lookup.node}else{node=path}FS.doTruncate(null,node,len)},ftruncate(fd,len){var stream=FS.getStreamChecked(fd);if(len<0||(stream.flags&2097155)===0){throw new FS.ErrnoError(28)}FS.doTruncate(stream,stream.node,len)},utime(path,atime,mtime,dontFollow){var lookup=FS.lookupPath(path,{follow:!dontFollow});FS.doSetAttr(null,lookup.node,{atime,mtime,dontFollow})},open(path,flags,mode=438){if(path===""){throw new FS.ErrnoError(44)}flags=FS_modeStringToFlags(flags);if(flags&64){mode=mode&4095|32768}else{mode=0}var node;var isDirPath;if(typeof path=="object"){node=path}else{isDirPath=path.endsWith("/");var lookup=FS.lookupPath(path,{follow:!(flags&131072),noent_okay:true});node=lookup.node;path=lookup.path}var created=false;if(flags&64){if(node){if(flags&128){throw new FS.ErrnoError(20)}}else if(isDirPath){throw new FS.ErrnoError(31)}else{node=FS.mknod(path,mode|511,0);created=true}}if(!node){throw new FS.ErrnoError(44)}if(FS.isChrdev(node.mode)){flags&=~512}if(flags&65536&&!FS.isDir(node.mode)){throw new FS.ErrnoError(54)}if(!created){var errCode=FS.mayOpen(node,flags);if(errCode){throw new FS.ErrnoError(errCode)}}if(flags&512&&!created){FS.truncate(node,0)}flags&=~(128|512|131072);var stream=FS.createStream({node,path:FS.getPath(node),flags,seekable:true,position:0,stream_ops:node.stream_ops,ungotten:[],error:false});if(stream.stream_ops.open){stream.stream_ops.open(stream)}if(created){FS.chmod(node,mode&511)}return stream},close(stream){if(FS.isClosed(stream)){throw new FS.ErrnoError(8)}if(stream.getdents)stream.getdents=null;stream.node?.notifyListeners(32);try{if(stream.stream_ops.close){stream.stream_ops.close(stream)}}catch(e){throw e}finally{FS.closeStream(stream.fd)}stream.fd=null},isClosed(stream){return stream.fd===null},llseek(stream,offset,whence){if(FS.isClosed(stream)){throw new FS.ErrnoError(8)}if(!stream.seekable||!stream.stream_ops.llseek){throw new FS.ErrnoError(70)}if(whence!=0&&whence!=1&&whence!=2){throw new FS.ErrnoError(28)}stream.position=stream.stream_ops.llseek(stream,offset,whence);stream.ungotten=[];return stream.position},read(stream,buffer,offset,length,position){if(length<0||position<0){throw new FS.ErrnoError(28)}if(FS.isClosed(stream)){throw new FS.ErrnoError(8)}if((stream.flags&2097155)===1){throw new FS.ErrnoError(8)}if(FS.isDir(stream.node.mode)){throw new FS.ErrnoError(31)}if(!stream.stream_ops.read){throw new FS.ErrnoError(28)}var seeking=typeof position!="undefined";if(!seeking){position=stream.position}else if(!stream.seekable){throw new FS.ErrnoError(70)}var bytesRead=stream.stream_ops.read(stream,buffer,offset,length,position);if(!seeking)stream.position+=bytesRead;return bytesRead},write(stream,buffer,offset,length,position,canOwn){if(length<0||position<0){throw new FS.ErrnoError(28)}if(FS.isClosed(stream)){throw new FS.ErrnoError(8)}if((stream.flags&2097155)===0){throw new FS.ErrnoError(8)}if(FS.isDir(stream.node.mode)){throw new FS.ErrnoError(31)}if(!stream.stream_ops.write){throw new FS.ErrnoError(28)}if(stream.seekable&&stream.flags&1024){FS.llseek(stream,0,2)}var seeking=typeof position!="undefined";if(!seeking){position=stream.position}else if(!stream.seekable){throw new FS.ErrnoError(70)}var bytesWritten=stream.stream_ops.write(stream,buffer,offset,length,position,canOwn);if(!seeking)stream.position+=bytesWritten;return bytesWritten},mmap(stream,length,position,prot,flags){if((prot&2)!==0&&(flags&2)===0&&(stream.flags&2097155)!==2){throw new FS.ErrnoError(2)}if((stream.flags&2097155)===1){throw new FS.ErrnoError(2)}if(!stream.stream_ops.mmap){throw new FS.ErrnoError(43)}if(!length){throw new FS.ErrnoError(28)}return stream.stream_ops.mmap(stream,length,position,prot,flags)},msync(stream,buffer,offset,length,mmapFlags){if(!stream.stream_ops.msync){return 0}return stream.stream_ops.msync(stream,buffer,offset,length,mmapFlags)},ioctl(stream,cmd,arg){if(!stream.stream_ops.ioctl){throw new FS.ErrnoError(59)}return stream.stream_ops.ioctl(stream,cmd,arg)},readFile(path,opts={}){opts.flags=opts.flags??0;opts.encoding=opts.encoding??"binary";if(opts.encoding!=="utf8"&&opts.encoding!=="binary"){abort(`Invalid encoding type "${opts.encoding}"`)}var stream=FS.open(path,opts.flags);var stat=FS.stat(path);var length=stat.size;var buf=new Uint8Array(length);FS.read(stream,buf,0,length,0);if(opts.encoding==="utf8"){buf=UTF8ArrayToString(buf)}FS.close(stream);return buf},writeFile(path,data,opts={}){opts.flags=opts.flags??577;var stream=FS.open(path,opts.flags,opts.mode);data=FS_fileDataToTypedArray(data);FS.write(stream,data,0,data.byteLength,undefined,opts.canOwn);FS.close(stream)},cwd:()=>FS.currentPath,chdir(path){var lookup=FS.lookupPath(path,{follow:true});if(lookup.node===null){throw new FS.ErrnoError(44)}if(!FS.isDir(lookup.node.mode)){throw new FS.ErrnoError(54)}var errCode=FS.nodePermissions(lookup.node,"x");if(errCode){throw new FS.ErrnoError(errCode)}FS.currentPath=lookup.path},createDefaultDirectories(){FS.mkdir("/tmp");FS.mkdir("/home");FS.mkdir("/home/web_user")},createDefaultDevices(){FS.mkdir("/dev");FS.registerDevice(FS.makedev(1,3),{read:()=>0,write:(stream,buffer,offset,length,pos)=>length,llseek:()=>0});FS.mkdev("/dev/null",FS.makedev(1,3));TTY.register(FS.makedev(5,0),TTY.default_tty_ops);TTY.register(FS.makedev(6,0),TTY.default_tty1_ops);FS.mkdev("/dev/tty",FS.makedev(5,0));FS.mkdev("/dev/tty1",FS.makedev(6,0));var randomBuffer=new Uint8Array(1024),randomLeft=0;var randomByte=()=>{if(randomLeft===0){randomFill(randomBuffer);randomLeft=randomBuffer.byteLength}return randomBuffer[--randomLeft]};FS.createDevice("/dev","random",randomByte);FS.createDevice("/dev","urandom",randomByte);FS.mkdir("/dev/shm");FS.mkdir("/dev/shm/tmp")},createSpecialDirectories(){FS.mkdir("/proc");var proc_self=FS.mkdir("/proc/self");FS.mkdir("/proc/self/fd");FS.mount({mount(){var node=FS.createNode(proc_self,"fd",16895,73);node.stream_ops={llseek:MEMFS.stream_ops.llseek};node.node_ops={lookup(parent,name){var fd=+name;var stream=FS.getStreamChecked(fd);var ret={parent:null,mount:{mountpoint:"fake"},node_ops:{readlink:()=>stream.path},id:fd+1};ret.parent=ret;return ret},readdir(){return Array.from(FS.streams.entries()).filter(([k,v])=>v).map(([k,v])=>k.toString())}};return node}},{},"/proc/self/fd")},createStandardStreams(input,output,error){if(input){FS.createDevice("/dev","stdin",input)}else{FS.symlink("/dev/tty","/dev/stdin")}if(output){FS.createDevice("/dev","stdout",null,output)}else{FS.symlink("/dev/tty","/dev/stdout")}if(error){FS.createDevice("/dev","stderr",null,error)}else{FS.symlink("/dev/tty1","/dev/stderr")}var stdin=FS.open("/dev/stdin",0);var stdout=FS.open("/dev/stdout",1);var stderr=FS.open("/dev/stderr",1)},staticInit(){FS.nameTable=new Array(4096);FS.mount(MEMFS,{},"/");FS.createDefaultDirectories();FS.createDefaultDevices();FS.createSpecialDirectories();FS.filesystems={MEMFS}},init(input,output,error){FS.initialized=true;input??=Module["stdin"];output??=Module["stdout"];error??=Module["stderr"];FS.createStandardStreams(input,output,error)},quit(){FS.initialized=false;for(var stream of FS.streams){if(stream){FS.close(stream)}}},findObject(path,dontResolveLastLink){var ret=FS.analyzePath(path,dontResolveLastLink);if(!ret.exists){return null}return ret.object},analyzePath(path,dontResolveLastLink){try{var lookup=FS.lookupPath(path,{follow:!dontResolveLastLink});path=lookup.path}catch(e){}var ret={isRoot:false,exists:false,error:0,name:null,path:null,object:null,parentExists:false,parentPath:null,parentObject:null};try{var lookup=FS.lookupPath(path,{parent:true});ret.parentExists=true;ret.parentPath=lookup.path;ret.parentObject=lookup.node;ret.name=PATH.basename(path);lookup=FS.lookupPath(path,{follow:!dontResolveLastLink});ret.exists=true;ret.path=lookup.path;ret.object=lookup.node;ret.name=lookup.node.name;ret.isRoot=lookup.path==="/"}catch(e){ret.error=e.errno}return ret},createPath(parent,path,canRead,canWrite){parent=typeof parent=="string"?parent:FS.getPath(parent);var parts=path.split("/").reverse();while(parts.length){var part=parts.pop();if(!part)continue;var current=PATH.join2(parent,part);try{FS.mkdir(current)}catch(e){if(e.errno!=20)throw e}parent=current}return current},createFile(parent,name,properties,canRead,canWrite){var path=PATH.join2(typeof parent=="string"?parent:FS.getPath(parent),name);var mode=FS_getMode(canRead,canWrite);return FS.create(path,mode)},createDataFile(parent,name,data,canRead,canWrite,canOwn){var path=name;if(parent){parent=typeof parent=="string"?parent:FS.getPath(parent);path=name?PATH.join2(parent,name):parent}var mode=FS_getMode(canRead,canWrite);var node=FS.create(path,mode);if(data){data=FS_fileDataToTypedArray(data);FS.chmod(node,mode|146);var stream=FS.open(node,577);FS.write(stream,data,0,data.length,0,canOwn);FS.close(stream);FS.chmod(node,mode)}},createDevice(parent,name,input,output){var path=PATH.join2(typeof parent=="string"?parent:FS.getPath(parent),name);var mode=FS_getMode(!!input,!!output);FS.createDevice.major??=64;var dev=FS.makedev(FS.createDevice.major++,0);FS.registerDevice(dev,{open(stream){stream.seekable=false},close(stream){if(output?.buffer?.length){output(10)}},read(stream,buffer,offset,length,pos){var bytesRead=0;for(var i=0;i<length;i++){var result;try{result=input()}catch(e){throw new FS.ErrnoError(29)}if(result===undefined&&bytesRead===0){throw new FS.ErrnoError(6)}if(result===null||result===undefined)break;bytesRead++;buffer[offset+i]=result}if(bytesRead){stream.node.atime=Date.now()}return bytesRead},write(stream,buffer,offset,length,pos){for(var i=0;i<length;i++){try{output(buffer[offset+i])}catch(e){throw new FS.ErrnoError(29)}}if(length){stream.node.mtime=stream.node.ctime=Date.now()}return i}});return FS.mkdev(path,mode,dev)},forceLoadFile(obj){if(obj.isDevice||obj.isFolder||obj.link||obj.contents)return true;if(globalThis.XMLHttpRequest){abort("Lazy loading should have been performed (contents set) in createLazyFile, but it was not. Lazy loading only works in web workers. Use --embed-file or --preload-file in emcc on the main thread.")}else{try{obj.contents=readBinary(obj.url)}catch(e){throw new FS.ErrnoError(29)}}},createLazyFile(parent,name,url,canRead,canWrite){class LazyUint8Array{lengthKnown=false;chunks=[];get(idx){if(idx>this.length-1||idx<0){return undefined}var chunkOffset=idx%this.chunkSize;var chunkNum=idx/this.chunkSize|0;return this.getter(chunkNum)[chunkOffset]}setDataGetter(getter){this.getter=getter}cacheLength(){var xhr=new XMLHttpRequest;xhr.open("HEAD",url,false);xhr.send(null);if(!(xhr.status>=200&&xhr.status<300||xhr.status===304))abort(`Couldn't load ${url}. Status: ${xhr.status}`);var datalength=Number(xhr.getResponseHeader("Content-length"));var header;var hasByteServing=(header=xhr.getResponseHeader("Accept-Ranges"))&&header==="bytes";var usesGzip=(header=xhr.getResponseHeader("Content-Encoding"))&&header==="gzip";var chunkSize=1024*1024;if(!hasByteServing)chunkSize=datalength;var doXHR=(from,to)=>{if(from>to)abort(`invalid range (${from}, ${to}) or no bytes requested!`);if(to>datalength-1)abort(`only ${datalength} bytes available! programmer error!`);var xhr=new XMLHttpRequest;xhr.open("GET",url,false);if(datalength!==chunkSize)xhr.setRequestHeader("Range",`bytes=${from}-${to}`);xhr.responseType="arraybuffer";if(xhr.overrideMimeType){xhr.overrideMimeType("text/plain; charset=x-user-defined")}xhr.send(null);if(!(xhr.status>=200&&xhr.status<300||xhr.status===304))abort(`Couldn't load ${url}. Status: ${xhr.status}`);if(xhr.response!==undefined){return new Uint8Array(xhr.response||[])}return intArrayFromString(xhr.responseText??"",true)};var lazyArray=this;lazyArray.setDataGetter(chunkNum=>{var start=chunkNum*chunkSize;var end=(chunkNum+1)*chunkSize-1;end=Math.min(end,datalength-1);if(typeof lazyArray.chunks[chunkNum]=="undefined"){lazyArray.chunks[chunkNum]=doXHR(start,end)}if(typeof lazyArray.chunks[chunkNum]=="undefined")abort("doXHR failed!");return lazyArray.chunks[chunkNum]});if(usesGzip||!datalength){chunkSize=datalength=1;datalength=this.getter(0).length;chunkSize=datalength;out("LazyFiles on gzip forces download of the whole file when length is accessed")}this._length=datalength;this._chunkSize=chunkSize;this.lengthKnown=true}get length(){if(!this.lengthKnown){this.cacheLength()}return this._length}get chunkSize(){if(!this.lengthKnown){this.cacheLength()}return this._chunkSize}}if(globalThis.XMLHttpRequest){if(!ENVIRONMENT_IS_WORKER)abort("Cannot do synchronous binary XHRs outside webworkers in modern browsers. Use --embed-file or --preload-file in emcc");var lazyArray=new LazyUint8Array;var properties={isDevice:false,contents:lazyArray}}else{var properties={isDevice:false,url}}var node=FS.createFile(parent,name,properties,canRead,canWrite);if(properties.contents){node.contents=properties.contents}else if(properties.url){node.contents=null;node.url=properties.url}Object.defineProperties(node,{usedBytes:{get:function(){return this.contents.length}}});var stream_ops={};for(const[key,fn]of Object.entries(node.stream_ops)){stream_ops[key]=(...args)=>{FS.forceLoadFile(node);return fn(...args)}}function writeChunks(stream,buffer,offset,length,position){var contents=stream.node.contents;if(position>=contents.length)return 0;var size=Math.min(contents.length-position,length);if(contents.slice){for(var i=0;i<size;i++){buffer[offset+i]=contents[position+i]}}else{for(var i=0;i<size;i++){buffer[offset+i]=contents.get(position+i)}}return size}stream_ops.read=(stream,buffer,offset,length,position)=>{FS.forceLoadFile(node);return writeChunks(stream,buffer,offset,length,position)};stream_ops.mmap=(stream,length,position,prot,flags)=>{FS.forceLoadFile(node);var ptr=mmapAlloc(length);if(!ptr){throw new FS.ErrnoError(48)}writeChunks(stream,HEAP8,ptr,length,position);return{ptr,allocated:true}};node.stream_ops=stream_ops;return node}};var HEAPU8;var UTF8ToString=(ptr,maxBytesToRead,ignoreNul)=>ptr?UTF8ArrayToString(HEAPU8,ptr,maxBytesToRead,ignoreNul):"";var HEAP32;var HEAPU32;var HEAP64;var SYSCALLS={currentUmask:18,calculateAt(dirfd,path,allowEmpty){if(PATH.isAbs(path)){return path}var dir;if(dirfd===-100){dir=FS.cwd()}else{var dirstream=SYSCALLS.getStreamFromFD(dirfd);dir=dirstream.path}if(path.length==0){if(!allowEmpty){throw new FS.ErrnoError(44)}return dir}return dir+"/"+path},writeStat(buf,stat){HEAPU32[buf>>2]=stat.dev;HEAPU32[buf+4>>2]=stat.mode;HEAPU32[buf+8>>2]=stat.nlink;HEAPU32[buf+12>>2]=stat.uid;HEAPU32[buf+16>>2]=stat.gid;HEAPU32[buf+20>>2]=stat.rdev;HEAP64[buf+24>>3]=BigInt(stat.size);HEAP32[buf+32>>2]=4096;HEAP32[buf+36>>2]=stat.blocks;var atime=stat.atime.getTime();var mtime=stat.mtime.getTime();var ctime=stat.ctime.getTime();HEAP64[buf+40>>3]=BigInt(Math.floor(atime/1e3));HEAPU32[buf+48>>2]=atime%1e3*1e3*1e3;HEAP64[buf+56>>3]=BigInt(Math.floor(mtime/1e3));HEAPU32[buf+64>>2]=mtime%1e3*1e3*1e3;HEAP64[buf+72>>3]=BigInt(Math.floor(ctime/1e3));HEAPU32[buf+80>>2]=ctime%1e3*1e3*1e3;HEAP64[buf+88>>3]=BigInt(stat.ino);return 0},writeStatFs(buf,stats){HEAPU32[buf+4>>2]=stats.bsize;HEAPU32[buf+60>>2]=stats.bsize;HEAP64[buf+8>>3]=BigInt(stats.blocks);HEAP64[buf+16>>3]=BigInt(stats.bfree);HEAP64[buf+24>>3]=BigInt(stats.bavail);HEAP64[buf+32>>3]=BigInt(stats.files);HEAP64[buf+40>>3]=BigInt(stats.ffree);HEAPU32[buf+48>>2]=stats.fsid;HEAPU32[buf+64>>2]=stats.flags;HEAPU32[buf+56>>2]=stats.namelen},doMsync(addr,stream,len,flags,offset){if(!FS.isFile(stream.node.mode)){throw new FS.ErrnoError(43)}if(flags&2){return 0}var buffer=HEAPU8.subarray(addr,addr+len);FS.msync(stream,buffer,offset,len,flags)},getStreamFromFD(fd){var stream=FS.getStreamChecked(fd);return stream},varargs:undefined,getStr(ptr){var ret=UTF8ToString(ptr);return ret}};function ___syscall_chdir(path){try{path=SYSCALLS.getStr(path);FS.chdir(path);return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_dup3(fd,newfd,flags){try{if(fd===newfd)return-28;if(flags&~524288)return-28;var old=SYSCALLS.getStreamFromFD(fd);if(newfd<0||newfd>=FS.MAX_OPEN_FDS)return-8;var existing=FS.getStream(newfd);if(existing)FS.close(existing);var stream=FS.dupStream(old,newfd);if(flags&524288){stream.flags|=524288}return stream.fd}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}var syscallGetVarargI=()=>{var ret=HEAP32[+SYSCALLS.varargs>>2];SYSCALLS.varargs+=4;return ret};var syscallGetVarargP=syscallGetVarargI;var HEAP16;function ___syscall_fcntl64(fd,cmd,varargs){SYSCALLS.varargs=varargs;try{var stream=SYSCALLS.getStreamFromFD(fd);switch(cmd){case 0:{var arg=syscallGetVarargI();if(arg<0){return-28}while(FS.streams[arg]){arg++}var newStream;newStream=FS.dupStream(stream,arg);return newStream.fd}case 1:case 2:return 0;case 3:return stream.flags;case 4:{var arg=syscallGetVarargI();var mask=289792;stream.flags=stream.flags&~mask|arg&mask;return 0}case 12:{var arg=syscallGetVarargP();var offset=0;HEAP16[arg+offset>>1]=2;return 0}case 13:case 14:return 0}return-28}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}var stringToUTF8=(str,outPtr,maxBytesToWrite)=>stringToUTF8Array(str,HEAPU8,outPtr,maxBytesToWrite);function ___syscall_getcwd(buf,size){try{if(size===0)return-28;var cwd=FS.cwd();var cwdLengthInBytes=lengthBytesUTF8(cwd)+1;if(size<cwdLengthInBytes)return-68;stringToUTF8(cwd,buf,size);return cwdLengthInBytes}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_getdents64(fd,dirp,count){try{var stream=SYSCALLS.getStreamFromFD(fd);stream.getdents||=FS.readdir(stream.path);var struct_size=280;var pos=0;var off=FS.llseek(stream,0,1);var startIdx=Math.floor(off/struct_size);var endIdx=Math.min(stream.getdents.length,startIdx+Math.floor(count/struct_size));for(var idx=startIdx;idx<endIdx;idx++){var id;var type;var name=stream.getdents[idx];if(name==="."){id=stream.node.id;type=4}else if(name===".."){var lookup=FS.lookupPath(stream.path,{parent:true});id=lookup.node.id;type=4}else{var child;try{child=FS.lookupNode(stream.node,name)}catch(e){if(e?.errno===28){continue}throw e}id=child.id;type=FS.isChrdev(child.mode)?2:FS.isDir(child.mode)?4:FS.isLink(child.mode)?10:8}HEAP64[dirp+pos>>3]=BigInt(id);HEAP64[dirp+pos+8>>3]=BigInt((idx+1)*struct_size);HEAP16[dirp+pos+16>>1]=280;HEAP8[dirp+pos+18]=type;stringToUTF8(name,dirp+pos+19,256);pos+=struct_size}FS.llseek(stream,idx*struct_size,0);return pos}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_ioctl(fd,op,varargs){SYSCALLS.varargs=varargs;try{var stream=SYSCALLS.getStreamFromFD(fd);switch(op){case 21509:{if(!stream.tty)return-59;return 0}case 21505:{if(!stream.tty)return-59;if(stream.tty.ops.ioctl_tcgets){var termios=stream.tty.ops.ioctl_tcgets(stream);var argp=syscallGetVarargP();HEAP32[argp>>2]=termios.c_iflag||0;HEAP32[argp+4>>2]=termios.c_oflag||0;HEAP32[argp+8>>2]=termios.c_cflag||0;HEAP32[argp+12>>2]=termios.c_lflag||0;for(var i=0;i<32;i++){HEAP8[argp+i+17]=termios.c_cc[i]||0}return 0}return 0}case 21510:case 21511:case 21512:{if(!stream.tty)return-59;return 0}case 21506:case 21507:case 21508:{if(!stream.tty)return-59;if(stream.tty.ops.ioctl_tcsets){var argp=syscallGetVarargP();var c_iflag=HEAP32[argp>>2];var c_oflag=HEAP32[argp+4>>2];var c_cflag=HEAP32[argp+8>>2];var c_lflag=HEAP32[argp+12>>2];var c_cc=[];for(var i=0;i<32;i++){c_cc.push(HEAP8[argp+i+17])}return stream.tty.ops.ioctl_tcsets(stream.tty,op,{c_iflag,c_oflag,c_cflag,c_lflag,c_cc})}return 0}case 21519:{if(!stream.tty)return-59;var argp=syscallGetVarargP();HEAP32[argp>>2]=0;return 0}case 21520:{if(!stream.tty)return-59;return-28}case 21537:case 21531:{var argp=syscallGetVarargP();return FS.ioctl(stream,op,argp)}case 21523:{if(!stream.tty)return-59;if(stream.tty.ops.ioctl_tiocgwinsz){var winsize=stream.tty.ops.ioctl_tiocgwinsz(stream.tty);var argp=syscallGetVarargP();HEAP16[argp>>1]=winsize[0];HEAP16[argp+2>>1]=winsize[1]}return 0}case 21524:{if(!stream.tty)return-59;return 0}case 21515:{if(!stream.tty)return-59;return 0}default:return-28}}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_mkdirat(dirfd,path,mode){try{path=SYSCALLS.getStr(path);path=SYSCALLS.calculateAt(dirfd,path);mode&=~SYSCALLS.currentUmask;FS.mkdir(path,mode,0);return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_openat(dirfd,path,flags,varargs){SYSCALLS.varargs=varargs;try{path=SYSCALLS.getStr(path);path=SYSCALLS.calculateAt(dirfd,path);var mode=varargs?syscallGetVarargI():0;if(flags&64){mode&=~SYSCALLS.currentUmask}return FS.open(path,flags,mode).fd}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}var pollOne=(fd,events)=>{var stream=FS.getStream(fd);if(!stream)return 32;var flags=stream.stream_ops?.poll?stream.stream_ops.poll(stream):5;return flags&(events|8|16|32)};var doPollSync=(fds,nfds)=>{var count=0;for(var i=0,pollfd=fds;i<nfds;i++,pollfd+=8){var revents=pollOne(HEAP32[pollfd>>2],HEAP16[pollfd+4>>1]);if(revents)count++;HEAP16[pollfd+6>>1]=revents}return count};function ___syscall_poll_nonblocking(fds,nfds){try{return doPollSync(fds,nfds)}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_renameat(olddirfd,oldpath,newdirfd,newpath){try{oldpath=SYSCALLS.getStr(oldpath);newpath=SYSCALLS.getStr(newpath);oldpath=SYSCALLS.calculateAt(olddirfd,oldpath);newpath=SYSCALLS.calculateAt(newdirfd,newpath);FS.rename(oldpath,newpath);return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_rmdir(path){try{path=SYSCALLS.getStr(path);FS.rmdir(path);return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_stat64(path,buf){try{path=SYSCALLS.getStr(path);return SYSCALLS.writeStat(buf,FS.stat(path))}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_statfs64(path,size,buf){try{SYSCALLS.writeStatFs(buf,FS.statfs(SYSCALLS.getStr(path)));return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}function ___syscall_unlinkat(dirfd,path,flags){try{path=SYSCALLS.getStr(path);path=SYSCALLS.calculateAt(dirfd,path);if(!flags){FS.unlink(path)}else if(flags===512){FS.rmdir(path)}else{return-28}return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return-e.errno}}var __abort_js=()=>abort("");var __emscripten_throw_longjmp=()=>{throw new EmscriptenSjLj};var _emscripten_get_now=()=>performance.now();var _emscripten_date_now=()=>Date.now();var nowIsMonotonic=1;var checkWasiClock=clock_id=>clock_id>=0&&clock_id<=3;var INT53_MAX=9007199254740992;var INT53_MIN=-9007199254740992;var bigintToI53Checked=num=>num<INT53_MIN||num>INT53_MAX?NaN:Number(num);function _clock_time_get(clk_id,ignored_precision,ptime){ignored_precision=bigintToI53Checked(ignored_precision);if(!checkWasiClock(clk_id)){return 28}var now;if(clk_id===0){now=_emscripten_date_now()}else if(nowIsMonotonic){now=_emscripten_get_now()}else{return 52}var nsec=Math.round(now*1e3*1e3);HEAP64[ptime>>3]=BigInt(nsec);return 0}var getHeapMax=()=>2147483648;var alignMemory=(size,alignment)=>Math.ceil(size/alignment)*alignment;var growMemory=size=>{var oldHeapSize=wasmMemory.buffer.byteLength;var pages=(size-oldHeapSize+65535)/65536|0;try{wasmMemory.grow(pages);updateMemoryViews();return 1}catch(e){}};var _emscripten_resize_heap=requestedSize=>{var oldSize=HEAPU8.length;requestedSize>>>=0;var maxHeapSize=getHeapMax();if(requestedSize>maxHeapSize){return false}for(var cutDown=1;cutDown<=4;cutDown*=2){var overGrownHeapSize=oldSize*(1+.2/cutDown);overGrownHeapSize=Math.min(overGrownHeapSize,requestedSize+100663296);var newSize=Math.min(maxHeapSize,alignMemory(Math.max(requestedSize,overGrownHeapSize),65536));var replacement=growMemory(newSize);if(replacement){return true}}return false};function _fd_close(fd){try{var stream=SYSCALLS.getStreamFromFD(fd);FS.close(stream);return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return e.errno}}var doReadv=(stream,iov,iovcnt,offset)=>{var ret=0;for(var i=0;i<iovcnt;i++){var ptr=HEAPU32[iov>>2];var len=HEAPU32[iov+4>>2];iov+=8;try{var curr=FS.read(stream,HEAP8,ptr,len,offset)}catch(e){if(ret>0&&e instanceof FS.ErrnoError&&(e.errno==6||e.errno==6)){break}throw e}if(curr<0)return-1;ret+=curr;if(curr<len)break;if(typeof offset!="undefined"){offset+=curr}}return ret};function _fd_read(fd,iov,iovcnt,pnum){try{var stream=SYSCALLS.getStreamFromFD(fd);var num=doReadv(stream,iov,iovcnt);HEAPU32[pnum>>2]=num;return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return e.errno}}function _fd_seek(fd,offset,whence,newOffset){offset=bigintToI53Checked(offset);try{if(isNaN(offset))return 22;var stream=SYSCALLS.getStreamFromFD(fd);FS.llseek(stream,offset,whence);HEAP64[newOffset>>3]=BigInt(stream.position);if(stream.getdents&&offset===0&&whence===0)stream.getdents=null;return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return e.errno}}function _fd_sync(fd){try{var stream=SYSCALLS.getStreamFromFD(fd);var rtn=stream.stream_ops?.fsync?.(stream);return rtn}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return e.errno}}var doWritev=(stream,iov,iovcnt,offset)=>{if(iovcnt==1){return FS.write(stream,HEAP8,HEAPU32[iov>>2],HEAPU32[iov+4>>2],offset)}var total=0;for(var i=0,p=iov;i<iovcnt;i++,p+=8){total+=HEAPU32[p+4>>2]}var view=new Uint8Array(total);var voff=0;for(var i=0;i<iovcnt;i++,iov+=8){var ptr=HEAPU32[iov>>2];var len=HEAPU32[iov+4>>2];view.set(HEAPU8.subarray(ptr,ptr+len),voff);voff+=len}return FS.write(stream,view,0,total,offset)};function _fd_write(fd,iov,iovcnt,pnum){try{var stream=SYSCALLS.getStreamFromFD(fd);var num=doWritev(stream,iov,iovcnt);HEAPU32[pnum>>2]=num;return 0}catch(e){if(typeof FS=="undefined"||!(e.name==="ErrnoError"))throw e;return e.errno}}var _mp_js_random_u32=()=>globalThis.crypto.getRandomValues(new Uint32Array(1))[0];var _mp_js_ticks_ms=()=>Date.now()-MP_JS_EPOCH;var _mp_js_time_ms=()=>Date.now();var getWasmTableEntry=funcPtr=>wasmTable.get(funcPtr);var HEAPF32;var HEAPF64;function setValue(ptr,value,type="i8"){if(type.endsWith("*"))type="*";switch(type){case"i1":HEAP8[ptr]=value;break;case"i8":HEAP8[ptr]=value;break;case"i16":HEAP16[ptr>>1]=value;break;case"i32":HEAP32[ptr>>2]=value;break;case"i64":HEAP64[ptr>>3]=BigInt(value);break;case"float":HEAPF32[ptr>>2]=value;break;case"double":HEAPF64[ptr>>3]=value;break;case"*":HEAPU32[ptr>>2]=value;break;default:abort(`invalid type for setValue: ${type}`)}}function getValue(ptr,type="i8"){if(type.endsWith("*"))type="*";switch(type){case"i1":return HEAP8[ptr];case"i8":return HEAP8[ptr];case"i16":return HEAP16[ptr>>1];case"i32":return HEAP32[ptr>>2];case"i64":return HEAP64[ptr>>3];case"float":return HEAPF32[ptr>>2];case"double":return HEAPF64[ptr>>3];case"*":return HEAPU32[ptr>>2];default:abort(`invalid type for getValue: ${type}`)}}var getCFunc=ident=>{var func=Module["_"+ident];return func};var writeArrayToMemory=(array,buffer)=>{HEAP8.set(array,buffer)};var stackAlloc=sz=>__emscripten_stack_alloc(sz);var stringToUTF8OnStack=str=>{var size=lengthBytesUTF8(str)+1;var ret=stackAlloc(size);stringToUTF8(str,ret,size);return ret};var ccall=(ident,returnType,argTypes,args,opts)=>{var toC={string:str=>{var ret=0;if(str!==null&&str!==undefined&&str!==0){ret=stringToUTF8OnStack(str)}return ret},array:arr=>{var ret=stackAlloc(arr.length);writeArrayToMemory(arr,ret);return ret}};function convertReturnValue(ret){if(returnType==="string"){return UTF8ToString(ret)}if(returnType==="boolean")return Boolean(ret);return ret}var func=getCFunc(ident);var cArgs=[];var stack=0;if(args){for(var i=0;i<args.length;i++){var converter=toC[argTypes[i]];if(converter){if(stack===0)stack=stackSave();cArgs[i]=converter(args[i])}else{cArgs[i]=args[i]}}}var ret=func(...cArgs);function onDone(ret){if(stack!==0)stackRestore(stack);return convertReturnValue(ret)}ret=onDone(ret);return ret};var cwrap=(ident,returnType,argTypes,opts)=>{var numericArgs=!argTypes||argTypes.every(type=>type==="number"||type==="boolean");var numericRet=returnType!=="string";if(numericRet&&numericArgs&&!opts){return getCFunc(ident)}return(...args)=>ccall(ident,returnType,argTypes,args,opts)};FS.createPreloadedFile=FS_createPreloadedFile;FS.preloadFile=FS_preloadFile;FS.staticInit();if(globalThis.crypto===undefined){globalThis.crypto=require("crypto")}var MP_JS_EPOCH=Date.now();{if(Module["noExitRuntime"])noExitRuntime=Module["noExitRuntime"];if(Module["print"])out=Module["print"];if(Module["printErr"])err=Module["printErr"];if(Module["arguments"])programArgs=Module["arguments"];if(Module["thisProgram"])thisProgram=Module["thisProgram"];var preInit=Module["preInit"];if(preInit){if(typeof preInit=="function")Module["preInit"]=preInit=[preInit];while(preInit.length>0){preInit.shift()()}}}Module["ccall"]=ccall;Module["cwrap"]=cwrap;Module["setValue"]=setValue;Module["getValue"]=getValue;Module["PATH"]=PATH;Module["PATH_FS"]=PATH_FS;Module["UTF8ToString"]=UTF8ToString;Module["stringToUTF8"]=stringToUTF8;Module["lengthBytesUTF8"]=lengthBytesUTF8;Module["FS"]=FS;function proxy_convert_mp_to_js_then_js_to_mp_obj_jsside(out){const ret=proxy_convert_mp_to_js_obj_jsside(out);proxy_convert_js_to_mp_obj_jsside_force_double_proxy(ret,out)}function proxy_convert_mp_to_js_then_js_to_js_then_js_to_mp_obj_jsside(out){const ret=proxy_convert_mp_to_js_obj_jsside(out);const js_obj=PyProxy.toJs(ret);proxy_convert_js_to_mp_obj_jsside(js_obj,out)}function js_get_proxy_js_ref_info(out){let used=0;for(const elem of proxy_js_ref){if(elem!==undefined){++used}}Module.setValue(out,proxy_js_ref.length,"i32");Module.setValue(out+4,used,"i32")}function has_attr(jsref,str){const base=proxy_js_ref[jsref];const attr=UTF8ToString(str);if(attr in base){return true}else{return false}}function lookup_attr(jsref,str,out){const base=proxy_js_ref[jsref];const attr=UTF8ToString(str);let value=base[attr];if(value!==undefined||attr in base){proxy_convert_js_to_mp_obj_jsside(value,out);if(typeof value==="function"&&!("_ref"in value)){return 2}else{return 1}}else{return 0}}function store_attr(jsref,attr_ptr,value_ref){const attr=UTF8ToString(attr_ptr);const value=proxy_convert_mp_to_js_obj_jsside(value_ref);proxy_js_ref[jsref][attr]=value}function call0(f_ref,out){const f=proxy_js_ref[f_ref];const ret=f();proxy_convert_js_to_mp_obj_jsside(ret,out)}function call1(f_ref,via_call,a0,out){const a0_js=proxy_convert_mp_to_js_obj_jsside(a0);const f=proxy_js_ref[f_ref];let ret;if(via_call){ret=f.call(a0_js)}else{ret=f(a0_js)}proxy_convert_js_to_mp_obj_jsside(ret,out)}function call2(f_ref,via_call,a0,a1,out){const a0_js=proxy_convert_mp_to_js_obj_jsside(a0);const a1_js=proxy_convert_mp_to_js_obj_jsside(a1);const f=proxy_js_ref[f_ref];let ret;if(via_call){ret=f.call(a0_js,a1_js)}else{ret=f(a0_js,a1_js)}proxy_convert_js_to_mp_obj_jsside(ret,out)}function calln(f_ref,via_call,n_args,value,out){const f=proxy_js_ref[f_ref];const a=[];for(let i=0;i<n_args;++i){const v=proxy_convert_mp_to_js_obj_jsside(value+i*3*4);a.push(v)}let ret;if(via_call){ret=f.call(...a)}else{ret=f(...a)}proxy_convert_js_to_mp_obj_jsside(ret,out)}function call0_kwarg(f_ref,via_call,n_kw,key,value,out){const f=proxy_js_ref[f_ref];const a={};for(let i=0;i<n_kw;++i){const k=UTF8ToString(getValue(key+i*4,"i32"));const v=proxy_convert_mp_to_js_obj_jsside(value+i*3*4);a[k]=v}let ret;if(via_call){ret=f.call(a)}else{ret=f(a)}proxy_convert_js_to_mp_obj_jsside(ret,out)}function calln_kwarg(f_ref,via_call,n_args,args_value,n_kw,kw_key,kw_value,out){const f=proxy_js_ref[f_ref];const a=[];for(let i=0;i<n_args;++i){const v=proxy_convert_mp_to_js_obj_jsside(args_value+i*3*4);a.push(v)}const ks={};for(let i=0;i<n_kw;++i){const k=UTF8ToString(getValue(kw_key+i*4,"i32"));const v=proxy_convert_mp_to_js_obj_jsside(kw_value+i*3*4);ks[k]=v}let ret;if(via_call){ret=f.call(...a,ks)}else{ret=f(...a,ks)}proxy_convert_js_to_mp_obj_jsside(ret,out)}function js_reflect_construct(f_ref,n_args,args,out){const f=proxy_js_ref[f_ref];const as=[];for(let i=0;i<n_args;++i){as.push(proxy_convert_mp_to_js_obj_jsside(args+i*3*4))}const ret=Reflect.construct(f,as);proxy_convert_js_to_mp_obj_jsside(ret,out)}function js_get_iter(f_ref,out){const f=proxy_js_ref[f_ref];const ret=f[Symbol.iterator]();proxy_convert_js_to_mp_obj_jsside(ret,out)}function js_iter_next(f_ref,out){const f=proxy_js_ref[f_ref];const ret=f.next();if(ret.done){return false}else{proxy_convert_js_to_mp_obj_jsside(ret.value,out);return true}}function js_subscr_load(f_ref,index_ref,out){const target=proxy_js_ref[f_ref];const index=python_index_semantics(target,proxy_convert_mp_to_js_obj_jsside(index_ref));const ret=target[index];proxy_convert_js_to_mp_obj_jsside(ret,out)}function js_subscr_store(f_ref,idx,value){const f=proxy_js_ref[f_ref];f[proxy_convert_mp_to_js_obj_jsside(idx)]=proxy_convert_mp_to_js_obj_jsside(value)}function proxy_js_free_obj(js_ref){if(js_ref>=PROXY_JS_REF_NUM_STATIC){proxy_js_ref_map.delete(proxy_js_ref[js_ref]);proxy_js_ref[js_ref]=undefined;if(js_ref<proxy_js_ref_next){proxy_js_ref_next=js_ref}}}function js_check_existing(c_ref){return proxy_js_check_existing(c_ref)}function js_get_error_info(jsref,out_name,out_message){const error=proxy_js_ref[jsref];proxy_convert_js_to_mp_obj_jsside(error.name,out_name);proxy_convert_js_to_mp_obj_jsside(error.message,out_message)}function js_then_resolve(ret_value,resolve){const ret_value_js=proxy_convert_mp_to_js_obj_jsside(ret_value);const resolve_js=proxy_convert_mp_to_js_obj_jsside(resolve);resolve_js(ret_value_js)}function js_then_reject(ret_value,reject){let ret_value_js;try{ret_value_js=proxy_convert_mp_to_js_obj_jsside(ret_value)}catch(error){ret_value_js=error}const reject_js=proxy_convert_mp_to_js_obj_jsside(reject);reject_js(ret_value_js)}function js_then_continue(jsref,py_resume,resolve,reject,out){const py_resume_js=proxy_convert_mp_to_js_obj_jsside(py_resume);const resolve_js=proxy_convert_mp_to_js_obj_jsside(resolve);const reject_js=proxy_convert_mp_to_js_obj_jsside(reject);const ret=proxy_js_ref[jsref].then(result=>{py_resume_js(result,null,resolve_js,reject_js)},reason=>{py_resume_js(null,reason,resolve_js,reject_js)});proxy_convert_js_to_mp_obj_jsside(ret,out)}function create_promise(out_set,out_promise){const out_set_js=proxy_convert_mp_to_js_obj_jsside(out_set);const promise=new Promise(out_set_js);proxy_convert_js_to_mp_obj_jsside(promise,out_promise)}var _free,_malloc,_mp_sched_keyboard_interrupt,_mp_js_init,_mp_js_register_js_module,_mp_js_do_import,_proxy_convert_mp_to_js_obj_cside,_mp_js_do_exec,_mp_js_do_exec_async,_mp_js_repl_init,_mp_js_repl_process_char,_mp_hal_get_interrupt_char,_proxy_c_init,_proxy_c_free_obj,_proxy_c_to_js_call,_proxy_c_to_js_dir,_proxy_c_to_js_has_attr,_proxy_c_to_js_lookup_attr,_proxy_c_to_js_store_attr,_proxy_c_to_js_delete_attr,_proxy_c_to_js_get_type,_proxy_c_to_js_get_array,_proxy_c_to_js_get_dict,_proxy_c_to_js_get_iter,_proxy_c_to_js_iternext,_proxy_c_to_js_resume,_setThrew,__emscripten_stack_restore,__emscripten_stack_alloc,_emscripten_stack_get_current,memory,__indirect_function_table,wasmMemory,wasmTable;function assignWasmExports(wasmExports){_free=Module["_free"]=wasmExports["ma"];_malloc=Module["_malloc"]=wasmExports["na"];_mp_sched_keyboard_interrupt=Module["_mp_sched_keyboard_interrupt"]=wasmExports["oa"];_mp_js_init=Module["_mp_js_init"]=wasmExports["pa"];_mp_js_register_js_module=Module["_mp_js_register_js_module"]=wasmExports["qa"];_mp_js_do_import=Module["_mp_js_do_import"]=wasmExports["ra"];_proxy_convert_mp_to_js_obj_cside=Module["_proxy_convert_mp_to_js_obj_cside"]=wasmExports["sa"];_mp_js_do_exec=Module["_mp_js_do_exec"]=wasmExports["ta"];_mp_js_do_exec_async=Module["_mp_js_do_exec_async"]=wasmExports["ua"];_mp_js_repl_init=Module["_mp_js_repl_init"]=wasmExports["va"];_mp_js_repl_process_char=Module["_mp_js_repl_process_char"]=wasmExports["wa"];_mp_hal_get_interrupt_char=Module["_mp_hal_get_interrupt_char"]=wasmExports["xa"];_proxy_c_init=Module["_proxy_c_init"]=wasmExports["ya"];_proxy_c_free_obj=Module["_proxy_c_free_obj"]=wasmExports["za"];_proxy_c_to_js_call=Module["_proxy_c_to_js_call"]=wasmExports["Aa"];_proxy_c_to_js_dir=Module["_proxy_c_to_js_dir"]=wasmExports["Ba"];_proxy_c_to_js_has_attr=Module["_proxy_c_to_js_has_attr"]=wasmExports["Ca"];_proxy_c_to_js_lookup_attr=Module["_proxy_c_to_js_lookup_attr"]=wasmExports["Da"];_proxy_c_to_js_store_attr=Module["_proxy_c_to_js_store_attr"]=wasmExports["Ea"];_proxy_c_to_js_delete_attr=Module["_proxy_c_to_js_delete_attr"]=wasmExports["Fa"];_proxy_c_to_js_get_type=Module["_proxy_c_to_js_get_type"]=wasmExports["Ga"];_proxy_c_to_js_get_array=Module["_proxy_c_to_js_get_array"]=wasmExports["Ha"];_proxy_c_to_js_get_dict=Module["_proxy_c_to_js_get_dict"]=wasmExports["Ia"];_proxy_c_to_js_get_iter=Module["_proxy_c_to_js_get_iter"]=wasmExports["Ja"];_proxy_c_to_js_iternext=Module["_proxy_c_to_js_iternext"]=wasmExports["Ka"];_proxy_c_to_js_resume=Module["_proxy_c_to_js_resume"]=wasmExports["La"];_setThrew=wasmExports["Ma"];__emscripten_stack_restore=wasmExports["Na"];__emscripten_stack_alloc=wasmExports["Oa"];_emscripten_stack_get_current=wasmExports["Pa"];memory=wasmMemory=wasmExports["ja"];__indirect_function_table=wasmTable=wasmExports["la"]}var wasmImports={K:___syscall_chdir,G:___syscall_dup3,l:___syscall_fcntl64,E:___syscall_getcwd,A:___syscall_getdents64,H:___syscall_ioctl,C:___syscall_mkdirat,o:___syscall_openat,B:___syscall_poll_nonblocking,z:___syscall_renameat,y:___syscall_rmdir,x:___syscall_stat64,w:___syscall_statfs64,v:___syscall_unlinkat,L:__abort_js,t:__emscripten_throw_longjmp,$:call0,ea:call0_kwarg,ca:call1,ba:call2,aa:calln,da:calln_kwarg,J:_clock_time_get,O:create_promise,I:_emscripten_date_now,u:_emscripten_resize_heap,j:_fd_close,n:_fd_read,D:_fd_seek,F:_fd_sync,k:_fd_write,Y:has_attr,V:invoke_fiii,s:invoke_i,b:invoke_ii,c:invoke_iii,a:invoke_iiii,f:invoke_iiiii,Q:invoke_iiiiii,g:invoke_v,h:invoke_vi,d:invoke_vii,e:invoke_viii,ia:invoke_viiii,S:js_check_existing,R:js_get_error_info,X:js_get_iter,fa:js_get_proxy_js_ref_info,T:js_iter_next,U:js_reflect_construct,_:js_subscr_load,Z:js_subscr_store,N:js_then_continue,M:js_then_reject,P:js_then_resolve,q:lookup_attr,r:_mp_js_random_u32,i:_mp_js_ticks_ms,m:_mp_js_time_ms,ga:proxy_convert_mp_to_js_then_js_to_js_then_js_to_mp_obj_jsside,ha:proxy_convert_mp_to_js_then_js_to_mp_obj_jsside,W:proxy_js_free_obj,p:store_attr};function invoke_ii(index,a1){var sp=stackSave();try{return getWasmTableEntry(index)(a1)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_iiii(index,a1,a2,a3){var sp=stackSave();try{return getWasmTableEntry(index)(a1,a2,a3)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_iii(index,a1,a2){var sp=stackSave();try{return getWasmTableEntry(index)(a1,a2)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_fiii(index,a1,a2,a3){var sp=stackSave();try{return getWasmTableEntry(index)(a1,a2,a3)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_viii(index,a1,a2,a3){var sp=stackSave();try{getWasmTableEntry(index)(a1,a2,a3)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_v(index){var sp=stackSave();try{getWasmTableEntry(index)()}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_iiiii(index,a1,a2,a3,a4){var sp=stackSave();try{return getWasmTableEntry(index)(a1,a2,a3,a4)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_vii(index,a1,a2){var sp=stackSave();try{getWasmTableEntry(index)(a1,a2)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_vi(index,a1){var sp=stackSave();try{getWasmTableEntry(index)(a1)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_i(index){var sp=stackSave();try{return getWasmTableEntry(index)()}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_viiii(index,a1,a2,a3,a4){var sp=stackSave();try{getWasmTableEntry(index)(a1,a2,a3,a4)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}function invoke_iiiiii(index,a1,a2,a3,a4,a5){var sp=stackSave();try{return getWasmTableEntry(index)(a1,a2,a3,a4,a5)}catch(e){stackRestore(sp);if(!(e instanceof EmscriptenEH))throw e;_setThrew(1,0)}}async function run(){preRun();if(runDependencies){await resolveRunDependencies()}var setStatus=Module["setStatus"];if(setStatus){setStatus("Running...");await new Promise(resolve=>setTimeout(resolve,1));setTimeout(setStatus,1,"")}if(ABORT)return;initRuntime();Module["onRuntimeInitialized"]?.();postRun()}var wasmExports;wasmExports=await createWasm();await run();
;return Module}export default _createMicroPythonModule;
/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2023-2024 Damien P. George
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

// Options:
// - pystack: size in words of the MicroPython Python stack.
// - heapsize: size in bytes of the MicroPython GC heap.
// - url: location to load `micropython.mjs`.
// - stdin: function to return input characters.
// - stdout: function that takes one argument, and is passed lines of stdout
//   output as they are produced.  By default this is handled by Emscripten
//   and in a browser goes to console, in node goes to process.stdout.write.
// - stderr: same behaviour as stdout but for error output.
// - linebuffer: whether to buffer line-by-line to stdout/stderr.
export async function loadMicroPython(options) {
    const { pystack, heapsize, url, stdin, stdout, stderr, linebuffer } =
        Object.assign(
            { pystack: 2 * 1024, heapsize: 1024 * 1024, linebuffer: true },
            options,
        );
    let Module = {};
    Module.locateFile = (path, scriptDirectory) =>
        url || scriptDirectory + path;
    Module._textDecoder = new TextDecoder();
    if (stdin !== undefined) {
        Module.stdin = stdin;
    }
    if (stdout !== undefined) {
        if (linebuffer) {
            Module._stdoutBuffer = [];
            Module.stdout = (c) => {
                if (c === 10) {
                    stdout(
                        Module._textDecoder.decode(
                            new Uint8Array(Module._stdoutBuffer),
                        ),
                    );
                    Module._stdoutBuffer = [];
                } else {
                    Module._stdoutBuffer.push(c);
                }
            };
        } else {
            Module.stdout = (c) => stdout(new Uint8Array([c]));
        }
    }
    if (stderr !== undefined) {
        if (linebuffer) {
            Module._stderrBuffer = [];
            Module.stderr = (c) => {
                if (c === 10) {
                    stderr(
                        Module._textDecoder.decode(
                            new Uint8Array(Module._stderrBuffer),
                        ),
                    );
                    Module._stderrBuffer = [];
                } else {
                    Module._stderrBuffer.push(c);
                }
            };
        } else {
            Module.stderr = (c) => stderr(new Uint8Array([c]));
        }
    }
    Module = await _createMicroPythonModule(Module);
    globalThis.Module = Module;
    proxy_js_init();
    const pyimport = (name) => {
        const value = Module._malloc(3 * 4);
        Module.ccall(
            "mp_js_do_import",
            "null",
            ["string", "pointer"],
            [name, value],
        );
        return proxy_convert_mp_to_js_obj_jsside_with_free(value);
    };
    Module.ccall(
        "mp_js_init",
        "null",
        ["number", "number"],
        [pystack, heapsize],
    );
    Module.ccall("proxy_c_init", "null", [], []);
    return {
        _module: Module,
        PyProxy: PyProxy,
        FS: Module.FS,
        globals: {
            __dict__: pyimport("__main__").__dict__,
            get(key) {
                return this.__dict__[key];
            },
            set(key, value) {
                this.__dict__[key] = value;
            },
            delete(key) {
                delete this.__dict__[key];
            },
        },
        registerJsModule(name, module) {
            const value = Module._malloc(3 * 4);
            proxy_convert_js_to_mp_obj_jsside(module, value);
            Module.ccall(
                "mp_js_register_js_module",
                "null",
                ["string", "pointer"],
                [name, value],
            );
            Module._free(value);
        },
        pyimport: pyimport,
        runPython(code) {
            const len = Module.lengthBytesUTF8(code);
            const buf = Module._malloc(len + 1);
            Module.stringToUTF8(code, buf, len + 1);
            const value = Module._malloc(3 * 4);
            Module.ccall(
                "mp_js_do_exec",
                "number",
                ["pointer", "number", "pointer"],
                [buf, len, value],
            );
            Module._free(buf);
            return proxy_convert_mp_to_js_obj_jsside_with_free(value);
        },
        runPythonAsync(code) {
            const len = Module.lengthBytesUTF8(code);
            const buf = Module._malloc(len + 1);
            Module.stringToUTF8(code, buf, len + 1);
            const value = Module._malloc(3 * 4);
            Module.ccall(
                "mp_js_do_exec_async",
                "number",
                ["pointer", "number", "pointer"],
                [buf, len, value],
            );
            Module._free(buf);
            const ret = proxy_convert_mp_to_js_obj_jsside_with_free(value);
            if (ret instanceof PyProxyThenable) {
                return Promise.resolve(ret);
            }
            return ret;
        },
        replInit() {
            Module.ccall("mp_js_repl_init", "null", ["null"]);
        },
        replProcessChar(chr) {
            return Module.ccall(
                "mp_js_repl_process_char",
                "number",
                ["number"],
                [chr],
            );
        },
        // Needed if the GC/asyncify is enabled.
        async replProcessCharWithAsyncify(chr) {
            return Module.ccall(
                "mp_js_repl_process_char",
                "number",
                ["number"],
                [chr],
                { async: true },
            );
        },
    };
}

globalThis.loadMicroPython = loadMicroPython;

async function runCLI() {
    const fs = await import("fs");
    let heap_size = 128 * 1024;
    let contents = "";
    let repl = true;

    for (let i = 2; i < process.argv.length; i++) {
        if (process.argv[i] === "-X" && i < process.argv.length - 1) {
            if (process.argv[i + 1].includes("heapsize=")) {
                heap_size = parseInt(process.argv[i + 1].split("heapsize=")[1]);
                const suffix = process.argv[i + 1].substr(-1).toLowerCase();
                if (suffix === "k") {
                    heap_size *= 1024;
                } else if (suffix === "m") {
                    heap_size *= 1024 * 1024;
                }
                ++i;
            }
        } else {
            contents += fs.readFileSync(process.argv[i], "utf8");
            repl = false;
        }
    }

    if (process.stdin.isTTY === false) {
        contents = fs.readFileSync(0, "utf8");
        repl = false;
    }

    const mp = await loadMicroPython({
        heapsize: heap_size,
        stdout: (data) => process.stdout.write(data),
        linebuffer: false,
    });

    if (repl) {
        mp.replInit();
        process.stdin.setRawMode(true);
        process.stdin.on("data", (data) => {
            for (let i = 0; i < data.length; i++) {
                mp.replProcessCharWithAsyncify(data[i]).then((result) => {
                    if (result) {
                        process.exit();
                    }
                });
            }
        });
    } else {
        // If the script to run ends with a running of the asyncio main loop, then inject
        // a simple `asyncio.run` hook that starts the main task.  This is primarily to
        // support running the standard asyncio tests.
        if (contents.endsWith("asyncio.run(main())\n")) {
            const asyncio = mp.pyimport("asyncio");
            asyncio.run = async (task) => {
                await asyncio.create_task(task);
            };
        }

        try {
            mp.runPython(contents);
        } catch (error) {
            if (error.name === "PythonError") {
                if (error.type === "SystemExit") {
                    // SystemExit, this is a valid exception to successfully end a script.
                } else {
                    // An unhandled Python exception, print in out.
                    console.error(error.message);
                }
            } else {
                // A non-Python exception.  Re-raise it.
                throw error;
            }
        }
    }
}

// Check if Node is running (equivalent to ENVIRONMENT_IS_NODE).
if (
    typeof process === "object" &&
    typeof process.versions === "object" &&
    typeof process.versions.node === "string"
) {
    // Check if this module is run from the command line via `node micropython.mjs`.
    //
    // See https://stackoverflow.com/questions/6398196/detect-if-called-through-require-or-directly-by-command-line/66309132#66309132
    //
    // Note:
    // - `resolve()` is used to handle symlinks
    // - `includes()` is used to handle cases where the file extension was omitted when passed to node

    if (process.argv.length > 1) {
        const path = await import("path");
        const url = await import("url");

        const pathToThisFile = path.resolve(url.fileURLToPath(import.meta.url));
        const pathPassedToNode = path.resolve(process.argv[1]);
        const isThisFileBeingRunViaCLI =
            pathToThisFile.includes(pathPassedToNode);

        if (isThisFileBeingRunViaCLI) {
            runCLI();
        }
    }
}
/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2023-2024 Damien P. George
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

class PyProxy {
    constructor(ref) {
        this._ref = ref;
    }

    // Convert js_obj -- which is possibly a PyProxy -- to a JavaScript object.
    static toJs(js_obj) {
        if (!(js_obj instanceof PyProxy)) {
            return js_obj;
        }

        const type = Module.ccall(
            "proxy_c_to_js_get_type",
            "number",
            ["number"],
            [js_obj._ref],
        );

        if (type === 1 || type === 2) {
            // List or tuple.
            const array_ref = Module._malloc(2 * 4);
            const item = Module._malloc(3 * 4);
            Module.ccall(
                "proxy_c_to_js_get_array",
                "null",
                ["number", "pointer"],
                [js_obj._ref, array_ref],
            );
            const len = Module.getValue(array_ref, "i32");
            const items_ptr = Module.getValue(array_ref + 4, "i32");
            const js_array = [];
            for (let i = 0; i < len; ++i) {
                Module.ccall(
                    "proxy_convert_mp_to_js_obj_cside",
                    "null",
                    ["pointer", "pointer"],
                    [Module.getValue(items_ptr + i * 4, "i32"), item],
                );
                const js_item = proxy_convert_mp_to_js_obj_jsside(item);
                js_array.push(PyProxy.toJs(js_item));
            }
            Module._free(array_ref);
            Module._free(item);
            return js_array;
        }

        if (type === 3) {
            // Dict.
            const map_ref = Module._malloc(2 * 4);
            const item = Module._malloc(3 * 4);
            Module.ccall(
                "proxy_c_to_js_get_dict",
                "null",
                ["number", "pointer"],
                [js_obj._ref, map_ref],
            );
            const alloc = Module.getValue(map_ref, "i32");
            const table_ptr = Module.getValue(map_ref + 4, "i32");
            const js_dict = {};
            for (let i = 0; i < alloc; ++i) {
                const mp_key = Module.getValue(table_ptr + i * 8, "i32");
                if (mp_key > 8) {
                    // Convert key to JS object.
                    Module.ccall(
                        "proxy_convert_mp_to_js_obj_cside",
                        "null",
                        ["pointer", "pointer"],
                        [mp_key, item],
                    );
                    const js_key = proxy_convert_mp_to_js_obj_jsside(item);

                    // Convert value to JS object.
                    const mp_value = Module.getValue(
                        table_ptr + i * 8 + 4,
                        "i32",
                    );
                    Module.ccall(
                        "proxy_convert_mp_to_js_obj_cside",
                        "null",
                        ["pointer", "pointer"],
                        [mp_value, item],
                    );
                    const js_value = proxy_convert_mp_to_js_obj_jsside(item);

                    // Populate JS dict.
                    js_dict[js_key] = PyProxy.toJs(js_value);
                }
            }
            Module._free(map_ref);
            Module._free(item);
            return js_dict;
        }

        // Cannot convert to JS, leave as a PyProxy.
        return js_obj;
    }
}

// This handler's goal is to allow minimal introspection
// of Python references from the JS world/utilities.
const py_proxy_handler = {
    isExtensible() {
        return true;
    },
    ownKeys(target) {
        const value = Module._malloc(3 * 4);
        Module.ccall(
            "proxy_c_to_js_dir",
            "null",
            ["number", "pointer"],
            [target._ref, value],
        );
        const dir = proxy_convert_mp_to_js_obj_jsside_with_free(value);
        return PyProxy.toJs(dir).filter((attr) => !attr.startsWith("__"));
    },
    getOwnPropertyDescriptor(target, prop) {
        return {
            value: target[prop],
            enumerable: true,
            writable: true,
            configurable: true,
        };
    },
    has(target, prop) {
        // avoid throwing on `Symbol() in proxy` checks
        if (typeof prop !== "string") {
            // returns true only on iterator because other
            // symbols are not considered in the `get` trap
            return prop === Symbol.iterator;
        }
        return Module.ccall(
            "proxy_c_to_js_has_attr",
            "number",
            ["number", "string"],
            [target._ref, prop],
        );
    },
    get(target, prop) {
        if (prop === "_ref") {
            return target._ref;
        }

        // ignore both then and all symbols but Symbol.iterator
        if (prop === "then" || typeof prop !== "string") {
            if (prop === Symbol.iterator) {
                // Get the Python object iterator, and return a JavaScript generator.
                const iter_ref = Module.ccall(
                    "proxy_c_to_js_get_iter",
                    "number",
                    ["number"],
                    [target._ref],
                );
                return function* () {
                    const value = Module._malloc(3 * 4);
                    while (true) {
                        const valid = Module.ccall(
                            "proxy_c_to_js_iternext",
                            "number",
                            ["number", "pointer"],
                            [iter_ref, value],
                        );
                        if (!valid) {
                            break;
                        }
                        yield proxy_convert_mp_to_js_obj_jsside(value);
                    }
                    Module._free(value);
                };
            }
            return undefined;
        }

        const value = Module._malloc(3 * 4);
        Module.ccall(
            "proxy_c_to_js_lookup_attr",
            "null",
            ["number", "string", "pointer"],
            [target._ref, prop, value],
        );
        return proxy_convert_mp_to_js_obj_jsside_with_free(value);
    },
    set(target, prop, value) {
        const value_conv = Module._malloc(3 * 4);
        proxy_convert_js_to_mp_obj_jsside(value, value_conv);
        const ret = Module.ccall(
            "proxy_c_to_js_store_attr",
            "number",
            ["number", "string", "number"],
            [target._ref, prop, value_conv],
        );
        Module._free(value_conv);
        return ret;
    },
    deleteProperty(target, prop) {
        return Module.ccall(
            "proxy_c_to_js_delete_attr",
            "number",
            ["number", "string"],
            [target._ref, prop],
        );
    },
};

// PyProxy of a Python generator, that implements the thenable interface.
class PyProxyThenable {
    constructor(ref) {
        this._ref = ref;
    }

    then(resolve, reject) {
        const values = Module._malloc(3 * 3 * 4);
        proxy_convert_js_to_mp_obj_jsside(resolve, values + 3 * 4);
        proxy_convert_js_to_mp_obj_jsside(reject, values + 2 * 3 * 4);
        Module.ccall(
            "proxy_c_to_js_resume",
            "null",
            ["number", "pointer"],
            [this._ref, values],
        );
        return proxy_convert_mp_to_js_obj_jsside_with_free(values);
    }
}
/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2023-2024 Damien P. George
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

// Number of static entries at the start of proxy_js_ref.
const PROXY_JS_REF_NUM_STATIC = 2;

// These constants should match the constants in proxy_c.c.

const PROXY_KIND_MP_EXCEPTION = -1;
const PROXY_KIND_MP_NULL = 0;
const PROXY_KIND_MP_NONE = 1;
const PROXY_KIND_MP_BOOL = 2;
const PROXY_KIND_MP_INT = 3;
const PROXY_KIND_MP_FLOAT = 4;
const PROXY_KIND_MP_STR = 5;
const PROXY_KIND_MP_CALLABLE = 6;
const PROXY_KIND_MP_GENERATOR = 7;
const PROXY_KIND_MP_OBJECT = 8;
const PROXY_KIND_MP_JSPROXY = 9;
const PROXY_KIND_MP_EXISTING = 10;

const PROXY_KIND_JS_UNDEFINED = 0;
const PROXY_KIND_JS_NULL = 1;
const PROXY_KIND_JS_BOOLEAN = 2;
const PROXY_KIND_JS_INTEGER = 3;
const PROXY_KIND_JS_DOUBLE = 4;
const PROXY_KIND_JS_STRING = 5;
const PROXY_KIND_JS_OBJECT_EXISTING = 6;
const PROXY_KIND_JS_OBJECT = 7;
const PROXY_KIND_JS_PYPROXY = 8;

class PythonError extends Error {
    constructor(exc_type, exc_details) {
        super(exc_details);
        this.name = "PythonError";
        this.type = exc_type;
    }
}

function proxy_js_init() {
    globalThis.proxy_js_ref = [globalThis, undefined];
    globalThis.proxy_js_ref_next = PROXY_JS_REF_NUM_STATIC;
    globalThis.proxy_js_ref_map = new Map();
    globalThis.proxy_js_ref_map.set(globalThis, 0);
    globalThis.proxy_js_map = new Map();
    globalThis.proxy_js_existing = [undefined];
    globalThis.pyProxyFinalizationRegistry = new FinalizationRegistry(
        (cRef) => {
            globalThis.proxy_js_map.delete(cRef);
            Module.ccall("proxy_c_free_obj", "null", ["number"], [cRef]);
        },
    );
}

// Check if the c_ref (Python proxy index) has a corresponding JavaScript-side PyProxy
// associated with it.  If so, take a concrete reference to this PyProxy from the WeakRef
// and put it in proxy_js_existing, to be referenced and reused by PROXY_KIND_MP_EXISTING.
function proxy_js_check_existing(c_ref) {
    const existing_obj = globalThis.proxy_js_map.get(c_ref)?.deref();
    if (existing_obj === undefined) {
        return -1;
    }

    // Search for a free slot in proxy_js_existing.
    for (let i = 0; i < globalThis.proxy_js_existing.length; ++i) {
        if (globalThis.proxy_js_existing[i] === undefined) {
            // Free slot found, put existing_obj here and return the index.
            globalThis.proxy_js_existing[i] = existing_obj;
            return i;
        }
    }

    // No free slot, so append to proxy_js_existing and return the new index.
    globalThis.proxy_js_existing.push(existing_obj);
    return globalThis.proxy_js_existing.length - 1;
}

// The `js_obj` argument cannot be `undefined`.
// Returns an integer reference to the given `js_obj`.
function proxy_js_add_obj(js_obj) {
    // Search for the first free slot in proxy_js_ref.
    while (proxy_js_ref_next < proxy_js_ref.length) {
        if (proxy_js_ref[proxy_js_ref_next] === undefined) {
            // Free slot found, reuse it.
            const id = proxy_js_ref_next;
            ++proxy_js_ref_next;
            proxy_js_ref[id] = js_obj;
            proxy_js_ref_map.set(js_obj, id);
            return id;
        }
        ++proxy_js_ref_next;
    }

    // No free slots, so grow proxy_js_ref by one (append at the end of the array).
    const id = proxy_js_ref.length;
    proxy_js_ref[id] = js_obj;
    proxy_js_ref_next = proxy_js_ref.length;
    proxy_js_ref_map.set(js_obj, id);
    return id;
}

function proxy_call_python(target, argumentsList) {
    let args = 0;

    // Strip trailing "undefined" arguments.
    while (
        argumentsList.length > 0 &&
        argumentsList[argumentsList.length - 1] === undefined
    ) {
        argumentsList.pop();
    }

    if (argumentsList.length > 0) {
        // TODO use stackAlloc/stackRestore?
        args = Module._malloc(argumentsList.length * 3 * 4);
        for (const i in argumentsList) {
            proxy_convert_js_to_mp_obj_jsside(
                argumentsList[i],
                args + i * 3 * 4,
            );
        }
    }
    const value = Module._malloc(3 * 4);
    Module.ccall(
        "proxy_c_to_js_call",
        "null",
        ["number", "number", "number", "pointer"],
        [target, argumentsList.length, args, value],
    );
    if (argumentsList.length > 0) {
        Module._free(args);
    }
    const ret = proxy_convert_mp_to_js_obj_jsside_with_free(value);
    if (ret instanceof PyProxyThenable) {
        // In Python when an async function is called it creates the
        // corresponding "generator", which must then be executed at
        // the top level by an asyncio-like scheduler.  In JavaScript
        // the semantics for async functions is that they are started
        // immediately (their non-async prefix code is executed immediately)
        // and only if they await do they return a Promise to delay the
        // execution of the remainder of the function.
        //
        // Emulate the JavaScript behaviour here by resolving the Python
        // async function.  We assume that the caller who gets this
        // return is JavaScript.
        return Promise.resolve(ret);
    }
    return ret;
}

function proxy_convert_js_to_mp_obj_jsside_helper(js_obj, out, allow_pyproxy) {
    let kind;
    if (js_obj === undefined) {
        kind = PROXY_KIND_JS_UNDEFINED;
    } else if (js_obj === null) {
        kind = PROXY_KIND_JS_NULL;
    } else if (typeof js_obj === "boolean") {
        kind = PROXY_KIND_JS_BOOLEAN;
        Module.setValue(out + 4, js_obj, "i32");
    } else if (typeof js_obj === "number") {
        if (Number.isInteger(js_obj)) {
            kind = PROXY_KIND_JS_INTEGER;
            Module.setValue(out + 4, js_obj, "i32");
        } else {
            kind = PROXY_KIND_JS_DOUBLE;
            // double must be stored to an address that's a multiple of 8
            const temp = (out + 4) & ~7;
            Module.setValue(temp, js_obj, "double");
            const double_lo = Module.getValue(temp, "i32");
            const double_hi = Module.getValue(temp + 4, "i32");
            Module.setValue(out + 4, double_lo, "i32");
            Module.setValue(out + 8, double_hi, "i32");
        }
    } else if (typeof js_obj === "string") {
        kind = PROXY_KIND_JS_STRING;
        const len = Module.lengthBytesUTF8(js_obj);
        const buf = Module._malloc(len + 1);
        Module.stringToUTF8(js_obj, buf, len + 1);
        Module.setValue(out + 4, len, "i32");
        Module.setValue(out + 8, buf, "i32");
    } else if (
        allow_pyproxy &&
        (js_obj instanceof PyProxy ||
            (typeof js_obj === "function" && "_ref" in js_obj) ||
            js_obj instanceof PyProxyThenable)
    ) {
        kind = PROXY_KIND_JS_PYPROXY;
        Module.setValue(out + 4, js_obj._ref, "i32");
    } else {
        let id;
        // See if there is an existing JsProxy reference, and use that if there is.
        const existing_ref = proxy_js_ref_map.get(js_obj);
        if (existing_ref !== undefined) {
            kind = PROXY_KIND_JS_OBJECT_EXISTING;
            id = existing_ref;
        } else {
            kind = PROXY_KIND_JS_OBJECT;
            id = proxy_js_add_obj(js_obj);
        }
        Module.setValue(out + 4, id, "i32");
    }
    Module.setValue(out + 0, kind, "i32");
}

function proxy_convert_js_to_mp_obj_jsside(js_obj, out) {
    proxy_convert_js_to_mp_obj_jsside_helper(js_obj, out, true);
}

function proxy_convert_js_to_mp_obj_jsside_force_double_proxy(js_obj, out) {
    proxy_convert_js_to_mp_obj_jsside_helper(js_obj, out, false);
}

function proxy_convert_mp_to_js_obj_jsside(value) {
    const kind = Module.getValue(value, "i32");
    let obj;
    if (kind === PROXY_KIND_MP_EXCEPTION) {
        // Exception
        const str_len = Module.getValue(value + 4, "i32");
        const str_ptr = Module.getValue(value + 8, "i32");
        const str = Module.UTF8ToString(str_ptr, str_len);
        Module._free(str_ptr);
        const str_split = str.split("\x04");
        throw new PythonError(str_split[0], str_split[1]);
    }
    if (kind === PROXY_KIND_MP_NULL) {
        // MP_OBJ_NULL
        throw new Error("NULL object");
    }
    if (kind === PROXY_KIND_MP_NONE) {
        // None
        obj = null;
    } else if (kind === PROXY_KIND_MP_BOOL) {
        // bool
        obj = Module.getValue(value + 4, "i32") ? true : false;
    } else if (kind === PROXY_KIND_MP_INT) {
        // int
        obj = Module.getValue(value + 4, "i32");
    } else if (kind === PROXY_KIND_MP_FLOAT) {
        // float
        // double must be loaded from an address that's a multiple of 8
        const temp = (value + 4) & ~7;
        const double_lo = Module.getValue(value + 4, "i32");
        const double_hi = Module.getValue(value + 8, "i32");
        Module.setValue(temp, double_lo, "i32");
        Module.setValue(temp + 4, double_hi, "i32");
        obj = Module.getValue(temp, "double");
    } else if (kind === PROXY_KIND_MP_STR) {
        // str
        const str_len = Module.getValue(value + 4, "i32");
        const str_ptr = Module.getValue(value + 8, "i32");
        obj = Module.UTF8ToString(str_ptr, str_len);
    } else if (kind === PROXY_KIND_MP_JSPROXY) {
        // js proxy
        const id = Module.getValue(value + 4, "i32");
        obj = proxy_js_ref[id];
    } else if (kind === PROXY_KIND_MP_EXISTING) {
        const id = Module.getValue(value + 4, "i32");
        obj = globalThis.proxy_js_existing[id];
        globalThis.proxy_js_existing[id] = undefined;
    } else {
        // obj
        const id = Module.getValue(value + 4, "i32");
        if (kind === PROXY_KIND_MP_CALLABLE) {
            obj = (...args) => {
                return proxy_call_python(id, args);
            };
            obj._ref = id;
        } else if (kind === PROXY_KIND_MP_GENERATOR) {
            obj = new PyProxyThenable(id);
        } else {
            // PROXY_KIND_MP_OBJECT
            const target = new PyProxy(id);
            obj = new Proxy(target, py_proxy_handler);
        }
        globalThis.pyProxyFinalizationRegistry.register(obj, id);
        globalThis.proxy_js_map.set(id, new WeakRef(obj));
    }
    return obj;
}

function proxy_convert_mp_to_js_obj_jsside_with_free(value) {
    const ret = proxy_convert_mp_to_js_obj_jsside(value);
    Module._free(value);
    return ret;
}

function python_index_semantics(target, index_in) {
    let index = index_in;
    if (typeof index === "number") {
        if (index < 0) {
            index += target.length;
        }
        if (index < 0 || index >= target.length) {
            throw new PythonError("IndexError", "index out of range");
        }
    }
    return index;
}
