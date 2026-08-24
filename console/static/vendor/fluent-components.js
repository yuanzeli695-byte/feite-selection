function g(t,e,r,o){var n=arguments.length,a=n<3?e:o===null?o=Object.getOwnPropertyDescriptor(e,r):o,i;if(typeof Reflect=="object"&&typeof Reflect.decorate=="function")a=Reflect.decorate(t,e,r,o);else for(var s=t.length-1;s>=0;s--)(i=t[s])&&(a=(n<3?i(a):n>3?i(e,r,a):i(e,r))||a);return n>3&&a&&Object.defineProperty(e,r,a),a}var ie=class{constructor(e,r,o=!1){this.evaluate=e,this.policy=r,this.isVolatile=o}};var b;(function(t){t[t.needsArrayObservation=1101]="needsArrayObservation",t[t.onlySetDOMPolicyOnce=1201]="onlySetDOMPolicyOnce",t[t.bindingInnerHTMLRequiresTrustedTypes=1202]="bindingInnerHTMLRequiresTrustedTypes",t[t.twoWayBindingRequiresObservables=1203]="twoWayBindingRequiresObservables",t[t.hostBindingWithoutHost=1204]="hostBindingWithoutHost",t[t.unsupportedBindingBehavior=1205]="unsupportedBindingBehavior",t[t.directCallToHTMLTagNotAllowed=1206]="directCallToHTMLTagNotAllowed",t[t.onlySetTemplatePolicyOnce=1207]="onlySetTemplatePolicyOnce",t[t.cannotSetTemplatePolicyAfterCompilation=1208]="cannotSetTemplatePolicyAfterCompilation",t[t.blockedByDOMPolicy=1209]="blockedByDOMPolicy",t[t.invalidHydrationAttributeMarker=1210]="invalidHydrationAttributeMarker",t[t.duplicateRenderInstruction=1211]="duplicateRenderInstruction",t[t.missingElementDefinition=1401]="missingElementDefinition",t[t.noRegistrationForContext=1501]="noRegistrationForContext",t[t.noFactoryForResolver=1502]="noFactoryForResolver",t[t.invalidResolverStrategy=1503]="invalidResolverStrategy",t[t.cannotAutoregisterDependency=1504]="cannotAutoregisterDependency",t[t.cannotResolveKey=1505]="cannotResolveKey",t[t.cannotConstructNativeFunction=1506]="cannotConstructNativeFunction",t[t.cannotJITRegisterNonConstructor=1507]="cannotJITRegisterNonConstructor",t[t.cannotJITRegisterIntrinsic=1508]="cannotJITRegisterIntrinsic",t[t.cannotJITRegisterInterface=1509]="cannotJITRegisterInterface",t[t.invalidResolver=1510]="invalidResolver",t[t.invalidKey=1511]="invalidKey",t[t.noDefaultResolver=1512]="noDefaultResolver",t[t.cyclicDependency=1513]="cyclicDependency",t[t.connectUpdateRequiresController=1514]="connectUpdateRequiresController"})(b||(b={}));var j=t=>typeof t=="function",C=t=>typeof t=="string",Vr=()=>{};var li=Object.create(null),S={warn(t,e){},error(t,e){return new Error(`Error ${t}`)},addMessages(t){Object.assign(li,t)}};var jr=Object.freeze([]);function ye(){let t=new Map;return Object.freeze({register(e){return t.has(e.type)?!1:(t.set(e.type,e),!0)},getByType(e){return t.get(e)},getForInstance(e){if(e!=null)return t.get(e.constructor)}})}function st(){let t=new WeakMap;return function(e){let r=t.get(e);if(r===void 0){let o=Reflect.getPrototypeOf(e);for(;r===void 0&&o!==null;)r=t.get(o),o=Reflect.getPrototypeOf(o);r=r===void 0?[]:r.slice(0),t.set(e,r)}return r}}function $(t){t.prototype.toJSON=Vr}var ct=class extends ie{createObserver(){return this}bind(e){return this.evaluate(e.source,e.context)}};$(ct);function dt(t,e){return new ct(t,e)}var ke=class{constructor(e,r){this.sub1=void 0,this.sub2=void 0,this.spillover=void 0,this.subject=e,this.sub1=r}has(e){return this.spillover===void 0?this.sub1===e||this.sub2===e:this.spillover.indexOf(e)!==-1}subscribe(e){let r=this.spillover;if(r===void 0){if(this.has(e))return;if(this.sub1===void 0){this.sub1=e;return}if(this.sub2===void 0){this.sub2=e;return}this.spillover=[this.sub1,this.sub2,e],this.sub1=void 0,this.sub2=void 0}else r.indexOf(e)===-1&&r.push(e)}unsubscribe(e){let r=this.spillover;if(r===void 0)this.sub1===e?this.sub1=void 0:this.sub2===e&&(this.sub2=void 0);else{let o=r.indexOf(e);o!==-1&&r.splice(o,1)}}notify(e){let r=this.spillover,o=this.subject;if(r===void 0){let n=this.sub1,a=this.sub2;n!==void 0&&n.handleChange(o,e),a!==void 0&&a.handleChange(o,e)}else for(let n=0,a=r.length;n<a;++n)r[n].handleChange(o,e)}},Pe=class{constructor(e){this.subscribers={},this.subjectSubscribers=null,this.subject=e}notify(e){var r,o;(r=this.subscribers[e])===null||r===void 0||r.notify(e),(o=this.subjectSubscribers)===null||o===void 0||o.notify(e)}subscribe(e,r){var o,n;let a;r?a=(o=this.subscribers[r])!==null&&o!==void 0?o:this.subscribers[r]=new ke(this.subject):a=(n=this.subjectSubscribers)!==null&&n!==void 0?n:this.subjectSubscribers=new ke(this.subject),a.subscribe(e)}unsubscribe(e,r){var o,n;r?(o=this.subscribers[r])===null||o===void 0||o.unsubscribe(e):(n=this.subjectSubscribers)===null||n===void 0||n.unsubscribe(e)}};var G=[],qt=[],si=globalThis.requestAnimationFrame,Kt=!0;function ci(){if(qt.length)throw qt.shift()}function di(t){try{t.call()}catch(e){if(Kt)qt.push(e),setTimeout(ci,0);else throw G.length=0,e}}function Yt(){let e=0;for(;e<G.length;)if(di(G[e]),e++,e>1024){for(let r=0,o=G.length-e;r<o;r++)G[r]=G[r+e];G.length-=e,e=0}G.length=0}function Gr(t){G.push(t),G.length<2&&(Kt?si(Yt):Yt())}var M=Object.freeze({enqueue:Gr,next:()=>new Promise(Gr),process:Yt,setMode:t=>Kt=t});var le=Object.freeze({unknown:void 0,coupled:1}),m=(()=>{let t=M.enqueue,e=/(:|&&|\|\||if|\?\.)/,r=new WeakMap,o,n=c=>{throw S.error(b.needsArrayObservation)};function a(c){var l;let p=(l=c.$fastController)!==null&&l!==void 0?l:r.get(c);return p===void 0&&(Array.isArray(c)?p=n(c):r.set(c,p=new Pe(c))),p}let i=st();class s{constructor(l){this.name=l,this.field=`_${l}`,this.callback=`${l}Changed`}getValue(l){return o!==void 0&&o.watch(l,this.name),l[this.field]}setValue(l,p){let f=this.field,x=l[f];if(x!==p){l[f]=p;let N=l[this.callback];j(N)&&N.call(l,x,p),a(l).notify(this.name)}}}class u extends ke{constructor(l,p,f=!1){super(l,p),this.expression=l,this.isVolatileBinding=f,this.needsRefresh=!0,this.needsQueue=!0,this.isAsync=!0,this.first=this,this.last=null,this.propertySource=void 0,this.propertyName=void 0,this.notifier=void 0,this.next=void 0}setMode(l){this.isAsync=this.needsQueue=l}bind(l){let p=this.observe(l.source,l.context);return!l.isBound&&this.requiresUnbind(l)&&l.onUnbind(this),p}requiresUnbind(l){return l.sourceLifetime!==le.coupled||this.first!==this.last||this.first.propertySource!==l.source}unbind(l){this.dispose()}observe(l,p){this.needsRefresh&&this.last!==null&&this.dispose();let f=o;o=this.needsRefresh?this:void 0,this.needsRefresh=this.isVolatileBinding;let x;try{x=this.expression(l,p)}finally{o=f}return x}disconnect(){this.dispose()}dispose(){if(this.last!==null){let l=this.first;for(;l!==void 0;)l.notifier.unsubscribe(this,l.propertyName),l=l.next;this.last=null,this.needsRefresh=this.needsQueue=this.isAsync}}watch(l,p){let f=this.last,x=a(l),N=f===null?this.first:{};if(N.propertySource=l,N.propertyName=p,N.notifier=x,x.subscribe(this,p),f!==null){if(!this.needsRefresh){let V;o=void 0,V=f.propertySource[f.propertyName],o=this,l===V&&(this.needsRefresh=!0)}f.next=N}this.last=N}handleChange(){this.needsQueue?(this.needsQueue=!1,t(this)):this.isAsync||this.call()}call(){this.last!==null&&(this.needsQueue=this.isAsync,this.notify(this))}*records(){let l=this.first;for(;l!==void 0;)yield l,l=l.next}}return $(u),Object.freeze({setArrayObserverFactory(c){n=c},getNotifier:a,track(c,l){o&&o.watch(c,l)},trackVolatile(){o&&(o.needsRefresh=!0)},notify(c,l){a(c).notify(l)},defineProperty(c,l){C(l)&&(l=new s(l)),i(c).push(l),Reflect.defineProperty(c,l.name,{enumerable:!0,get(){return l.getValue(this)},set(p){l.setValue(this,p)}})},getAccessors:i,binding(c,l,p=this.isVolatileBinding(c)){return new u(c,l,p)},isVolatileBinding(c){return e.test(c.toString())}})})();function je(t,e){m.defineProperty(t,e)}var Wr=(()=>{let t=null;return{get(){return t},set(e){t=e}}})(),q=Object.freeze({default:{index:0,length:0,get event(){return q.getEvent()},eventDetail(){return this.event.detail},eventTarget(){return this.event.target}},getEvent(){return Wr.get()},setEvent(t){Wr.set(t)}});var Jt=class extends ie{createObserver(e){return m.binding(this.evaluate,e,this.isVolatile)}};function ut(t,e,r=m.isVolatileBinding(t)){return new Jt(t,e,r)}var P=Object.freeze({none:0,attribute:1,booleanAttribute:2,property:3,content:4,tokenList:5,event:6}),Xr=t=>t,ui=globalThis.trustedTypes?globalThis.trustedTypes.createPolicy("fast-element",{createHTML:Xr}):{createHTML:Xr},pt=Object.freeze({createHTML(t){return ui.createHTML(t)},protect(t,e,r,o){return o}}),pi=pt,Y=Object.freeze({get policy(){return pt},setPolicy(t){if(pt!==pi)throw S.error(b.onlySetDOMPolicyOnce);pt=t},setAttribute(t,e,r){r==null?t.removeAttribute(e):t.setAttribute(e,r)},setBooleanAttribute(t,e,r){r?t.setAttribute(e,""):t.removeAttribute(e)}});var Qt="boolean",Ur="reflect",Ne=Object.freeze({locate:st()}),Yr={toView(t){return t?"":null},fromView(t){return!!t}};function qr(t){if(t==null)return null;let e=t*1;return isNaN(e)?null:e}var We={toView(t){let e=qr(t);return e&&e.toString()},fromView:qr},Ge=class t{constructor(e,r,o=r.toLowerCase(),n=Ur,a){this.guards=new Set,this.Owner=e,this.name=r,this.attribute=o,this.mode=n,this.converter=a,this.fieldName=`_${r}`,this.callbackName=`${r}Changed`,this.hasCallback=this.callbackName in e.prototype,n===Qt&&a===void 0&&(this.converter=Yr)}setValue(e,r){let o=e[this.fieldName],n=this.converter;n!==void 0&&(r=n.fromView(r)),o!==r&&(e[this.fieldName]=r,this.tryReflectToAttribute(e),this.hasCallback&&e[this.callbackName](o,r),e.$fastController.notify(this.name))}getValue(e){return m.track(e,this.name),e[this.fieldName]}onAttributeChangedCallback(e,r){this.guards.has(e)||(this.guards.add(e),this.mode===Qt?this.setValue(e,r!==null):this.setValue(e,r),this.guards.delete(e))}tryReflectToAttribute(e){let r=this.mode,o=this.guards;o.has(e)||r==="fromView"||M.enqueue(()=>{o.add(e);let n=e[this.fieldName];switch(r){case Ur:{let a=this.converter;Y.setAttribute(e,this.attribute,a!==void 0?a.toView(n):n);break}case Qt:Y.setBooleanAttribute(e,this.attribute,n);break}o.delete(e)})}static collect(e,...r){let o=[];r.push(Ne.locate(e));for(let n=0,a=r.length;n<a;++n){let i=r[n];if(i!==void 0)for(let s=0,u=i.length;s<u;++s){let c=i[s];C(c)?o.push(new t(e,c)):o.push(new t(e,c.property,c.attribute,c.mode,c.converter))}}return o}};function h(t,e){let r;function o(n,a){arguments.length>1&&(r.property=a),Ne.locate(n.constructor).push(r)}if(arguments.length>1){r={},o(t,e);return}return r=t===void 0?{}:t,o}var Zt;function Kr(t){return t.reduce((e,r)=>(r instanceof H?e.push(...Kr(r.styles)):e.push(r),e),[])}var H=class t{get strategy(){return this._strategy===null&&(Zt||t.setDefaultStrategy(t.supportsAdoptedStyleSheets?gi():fi()),this.withStrategy(Zt)),this._strategy}constructor(e){this.styles=e,this.targets=new WeakSet,this._strategy=null}addStylesTo(e){this.strategy.addStylesTo(e),this.targets.add(e)}removeStylesFrom(e){this.strategy.removeStylesFrom(e),this.targets.delete(e)}isAttachedTo(e){return this.targets.has(e)}withStrategy(e){return this._strategy=new e(Kr(this.styles)),this}static setDefaultStrategy(e){Zt=e}static normalize(e){return e===void 0?void 0:Array.isArray(e)?new t(e):e instanceof t?e:new t([e])}};H.supportsAdoptedStyleSheets=Array.isArray(document.adoptedStyleSheets)&&"replace"in CSSStyleSheet.prototype;function gi(){let t=new Map;return class{constructor(r){this.sheets=r.map(o=>{if(o instanceof CSSStyleSheet)return o;let n=t.get(o);return n===void 0&&(n=new CSSStyleSheet,n.replaceSync(o),t.set(o,n)),n})}addStylesTo(r){let o=r;o.adoptedStyleSheets=[...o.adoptedStyleSheets,...this.sheets]}removeStylesFrom(r){let o=r;o.adoptedStyleSheets=o.adoptedStyleSheets.filter(n=>this.sheets.indexOf(n)===-1)}}}var hi=0;function fi(){return class{constructor(e){this.styles=e,this.styleClass=`fast-${++hi}`}addStylesTo(e){let r=e===document?document.body:e;for(let o=0;o<this.styles.length;o++){let n=document.createElement("style");n.innerHTML=this.styles[o],n.className=this.styleClass,r.append(n)}}removeStylesFrom(e){let r=e===document?document.body:e,o=r.querySelectorAll(`.${this.styleClass}`);for(let n=0,a=o.length;n<a;++n)r.removeChild(o[n])}}}var mi={},Jr=new WeakMap,er=ye(),Fe=Object.freeze({register(t){if(!er.register(t))return!1;let e=Zr(t.registry);return Object.prototype.hasOwnProperty.call(e,t.name)||m.defineProperty(e,t.name),e[t.name]=t.type,!0},getByType:er.getByType,getForInstance:er.getForInstance,whenRegistered:vi});function Zr(t=customElements){if(t===customElements)return mi;let e=Jr.get(t);return e||(e={},Jr.set(t,e)),e}function Qr(t){return t===void 0?void 0:Fe.getByType(t)}function vi(t,e=customElements){let r=Zr(e);Object.prototype.hasOwnProperty.call(r,t)||m.defineProperty(r,t);let o=Qr(r[t]);return o!==void 0?Promise.resolve(o):new Promise(n=>{let a=m.getNotifier(r),i={handleChange:()=>{let s=Qr(r[t]);s!==void 0&&(a.unsubscribe(i,t),n(s))}};a.subscribe(i,t)})}var eo={mode:"open"},to={},ro=new Set,ht=new WeakMap,gt=new WeakMap,he=new WeakMap,oo=new WeakMap,bi=new WeakMap;function Bi(t){return j(t)}function xi(t){return typeof t?.then=="function"}function no(t,e){if(gt.delete(t),t.template===void 0&&e!==void 0&&(t.template=e),t.template!==void 0)return he.delete(t),ht.delete(t),t.template}function tr(t,e=t.registry,r){if(!r?.length)return;let o=t,n=oo.get(o);if(!n?.has(e)){n===void 0&&(n=new WeakSet,oo.set(o,n)),n.add(e);for(let a of r)a(t)}}function ft(t){var e;return(e=bi.get(t))!==null&&e!==void 0?e:null}function rr(t){if(t.template!==void 0)return he.delete(t),t.template;let e=gt.get(t);if(e)return e;let r=ht.get(t);if(!r)return;he.delete(t);let o;try{o=r(t)}catch(n){throw he.set(t,n),n}if(xi(o)){let n=Promise.resolve(o).then(a=>no(t,a)).catch(a=>{throw gt.delete(t),he.set(t,a),a});return gt.set(t,n),n}return no(t,o)}function Si(t,e){let r=t;if(e===void 0){he.delete(r);return}he.set(r,e)}var R=class t{get isDefined(){return this.platformDefined}constructor(e,r=e.definition){var o;this.platformDefined=!1,C(r)&&(r={name:r}),this.type=e,this.name=r.name,this.registry=(o=r.registry)!==null&&o!==void 0?o:customElements,Bi(r.template)?ht.set(this,r.template):this.template=r.template;let n=e.prototype,a=Ge.collect(e,r.attributes),i=new Array(a.length),s={},u={};for(let c=0,l=a.length;c<l;++c){let p=a[c];i[c]=p.attribute,s[p.name]=p,u[p.attribute]=p,m.defineProperty(n,p)}Reflect.defineProperty(e,"observedAttributes",{value:i,enumerable:!0}),this.attributes=a,this.propertyLookup=s,this.attributeLookup=u,this.shadowOptions=r.shadowOptions===void 0?eo:r.shadowOptions===null?void 0:Object.assign(Object.assign({},eo),r.shadowOptions),this.elementOptions=r.elementOptions===void 0?to:Object.assign(Object.assign({},to),r.elementOptions),this.styles=H.normalize(r.styles),this.schema=r.schema,Fe.register(this)}define(e=this.registry,r){let o=this.type;if(!e.get(this.name)){if(tr(this,e,r),this.template===void 0&&ht.has(this))return Promise.resolve().then(()=>rr(this)).then(n=>{n!==void 0&&!e.get(this.name)&&(this.platformDefined=!0,e.define(this.name,o,this.elementOptions))}).catch(n=>{Si(this,n),m.notify(this,"template")}),this;this.platformDefined=!0,e.define(this.name,o,this.elementOptions)}return this}static compose(e,r){let o=ro.has(e)||Fe.getByType(e)?new t(class extends e{},r):new t(e,r);return Promise.resolve(o)}static registerBaseType(e){ro.add(e)}};R.getByType=Fe.getByType;R.getForInstance=Fe.getForInstance;m.defineProperty(R.prototype,"template");var yi={bubbles:!0,composed:!0,cancelable:!0},or="isConnected",lo=new WeakMap,nr=Symbol("fast-late-attribute-observer");function mt(t){var e,r;return(r=(e=t.shadowRoot)!==null&&e!==void 0?e:lo.get(t))!==null&&r!==void 0?r:null}var ao,D;(function(t){t[t.connecting=0]="connecting",t[t.connected=1]="connected",t[t.disconnecting=2]="disconnecting",t[t.disconnected=3]="disconnected"})(D||(D={}));var se=class t{get isConnected(){return m.track(this,or),this.stage===D.connected}get context(){var e,r;return(r=(e=this.view)===null||e===void 0?void 0:e.context)!==null&&r!==void 0?r:q.default}get isBound(){var e,r;return(r=(e=this.view)===null||e===void 0?void 0:e.isBound)!==null&&r!==void 0?r:!1}get sourceLifetime(){var e;return(e=this.view)===null||e===void 0?void 0:e.sourceLifetime}get template(){var e;if(this._template===null){let r=this.definition;this.source.resolveTemplate?this._template=this.source.resolveTemplate():r.template&&(this._template=(e=r.template)!==null&&e!==void 0?e:null)}return this._template}set template(e){this._template!==e&&(this._template=e,this.needsInitialization||this.renderTemplate(e))}get shadowOptions(){return this._shadowRootOptions}set shadowOptions(e){if(this._shadowRootOptions===void 0&&e!==void 0){this._shadowRootOptions=e;let r=this.source.shadowRoot;r?this.hasExistingShadowRoot=!0:(r=this.source.attachShadow(e),e.mode==="closed"&&lo.set(this.source,r))}}get mainStyles(){var e;if(this._mainStyles===null){let r=this.definition;this.source.resolveStyles?this._mainStyles=this.source.resolveStyles():r.styles&&(this._mainStyles=(e=r.styles)!==null&&e!==void 0?e:null)}return this._mainStyles}set mainStyles(e){this._mainStyles!==e&&(this._mainStyles!==null&&this.removeStyles(this._mainStyles),this._mainStyles=e,this.needsInitialization||this.addStyles(e))}constructor(e,r){this.boundObservables=null,this.needsInitialization=!0,this.hasExistingShadowRoot=!1,this.isPrerendered=new Promise(a=>{this._resolvePrerendered=a}),this.isHydrated=new Promise(a=>{this._resolveHydrated=a}),this._template=null,this.stage=D.disconnected,this.guardBehaviorConnection=!1,this.behaviors=null,this.behaviorsConnected=!1,this._mainStyles=null,this.$fastController=this,this.view=null,this._notifier=new Pe(e),this.source=e,this.definition=r,this.shadowOptions=r.shadowOptions;let o=Reflect.getPrototypeOf(e),n=o===null?[]:m.getAccessors(o);if(n.length>0){let a=this.boundObservables=Object.create(null);for(let i=0,s=n.length;i<s;++i){let u=n[i].name,c=e[u];c!==void 0&&(delete e[u],a[u]=c)}Object.keys(a).length===0&&(this.boundObservables=null)}this.captureBoundObservables()}get subject(){return this._notifier.subject}notify(e){this._notifier.notify(e)}subscribe(e,r){this._notifier.subscribe(e,r)}unsubscribe(e,r){this._notifier.unsubscribe(e,r)}onUnbind(e){var r;(r=this.view)===null||r===void 0||r.onUnbind(e)}addBehavior(e){var r,o;let n=(r=this.behaviors)!==null&&r!==void 0?r:this.behaviors=new Map,a=(o=n.get(e))!==null&&o!==void 0?o:0;a===0?(n.set(e,1),e.addedCallback&&e.addedCallback(this),e.connectedCallback&&!this.guardBehaviorConnection&&(this.stage===D.connected||this.stage===D.connecting)&&e.connectedCallback(this)):n.set(e,a+1)}removeBehavior(e,r=!1){let o=this.behaviors;if(o===null)return;let n=o.get(e);n!==void 0&&(n===1||r?(o.delete(e),e.disconnectedCallback&&this.stage!==D.disconnected&&e.disconnectedCallback(this),e.removedCallback&&e.removedCallback(this)):o.set(e,n-1))}addStyles(e){var r;if(!e)return;let o=this.source;e instanceof HTMLElement?((r=mt(o))!==null&&r!==void 0?r:this.source).append(e):e.isAttachedTo(o)||e.addStylesTo(o)}removeStyles(e){var r;if(!e)return;let o=this.source;e instanceof HTMLElement?((r=mt(o))!==null&&r!==void 0?r:o).removeChild(e):e.isAttachedTo(o)&&e.removeStylesFrom(o)}connect(){this.stage===D.disconnected&&(this.stage=D.connecting,this.captureBoundObservables(),this.syncLateAttributes(),this.observeLateAttributes(),this.bindObservables(),this.connectBehaviors(),this.needsInitialization?(this.renderTemplate(this.template),this.addStyles(this.mainStyles),this.needsInitialization=!1):this.view!==null&&this.view.bind(this.source),this.stage=D.connected,m.notify(this,or))}bindObservables(){if(this.boundObservables!==null){let e=this.source,r=this.boundObservables,o=Object.keys(r);for(let n=0,a=o.length;n<a;++n){let i=o[n];e[i]=r[i]}this.boundObservables=null}}captureBoundObservables(){let e=this.source,r=Object.getOwnPropertyNames(e),o=a=>{let i=Reflect.getPrototypeOf(e);for(;i!==null;){let s=Reflect.getOwnPropertyDescriptor(i,a);if(s?.get||s?.set)return!0;i=Reflect.getPrototypeOf(i)}return!1},n=this.boundObservables;for(let a=0,i=r.length;a<i;++a){let u=r[a];if(!o(u))continue;let c=e[u];if(c===void 0){delete e[u];continue}delete e[u],(n??(n=this.boundObservables=Object.create(null)))[u]=c}}syncLateAttributes(){let e=ft(this.definition);if(e!==null)for(let r of Object.keys(e))this.source.hasAttribute(r)&&this.onAttributeChangedCallback(r,null,this.source.getAttribute(r))}observeLateAttributes(){let e=ft(this.definition);if(e===null)return;let r=this.source;r[nr]===void 0&&(r[nr]=new MutationObserver(o=>{let n=r.$fastController,a=ft(n.definition);if(a!==null)for(let i=0,s=o.length;i<s;++i){let u=o[i].attributeName;u===null||a[u]===void 0||n.onAttributeChangedCallback(u,null,r.getAttribute(u))}}),r[nr].observe(r,{attributes:!0,attributeFilter:Object.keys(e)}))}connectBehaviors(){if(this.behaviorsConnected===!1){let e=this.behaviors;if(e!==null){this.guardBehaviorConnection=!0;for(let r of e.keys())r.connectedCallback&&r.connectedCallback(this);this.guardBehaviorConnection=!1}this.behaviorsConnected=!0}}disconnectBehaviors(){if(this.behaviorsConnected===!0){let e=this.behaviors;if(e!==null)for(let r of e.keys())r.disconnectedCallback&&r.disconnectedCallback(this);this.behaviorsConnected=!1}}disconnect(){this.stage===D.connected&&(this.stage=D.disconnecting,m.notify(this,or),this.view!==null&&this.view.unbind(),this.disconnectBehaviors(),this.stage=D.disconnected)}onAttributeChangedCallback(e,r,o){let n=this.definition.attributeLookup[e];n!==void 0&&n.onAttributeChangedCallback(this.source,o)}emit(e,r,o){return this.stage===D.connected?this.source.dispatchEvent(new CustomEvent(e,Object.assign(Object.assign({detail:r},yi),o))):!1}renderTemplate(e){var r;let o=this.source,n=(r=mt(o))!==null&&r!==void 0?r:o;if(this.view!==null)this.view.dispose(),this.view=null;else if((!this.needsInitialization||this.hasExistingShadowRoot)&&(!this.hasExistingShadowRoot||!this.needsInitialization))for(let a=n.firstChild;a!==null;a=n.firstChild)n.removeChild(a);if(e){let a=this.hasExistingShadowRoot&&this.needsInitialization,i=!1;a&&t.hydrationHook&&(i=t.hydrationHook(this,e,o,n)),i||this.renderClientSide(e,o,n),this._resolvePrerendered(a),this._resolveHydrated(i)}else this.needsInitialization&&(this._resolvePrerendered(!1),this._resolveHydrated(!1))}renderClientSide(e,r,o){if(this.hasExistingShadowRoot){for(let n=o.firstChild;n!==null;n=o.firstChild)o.removeChild(n);this.hasExistingShadowRoot=!1}this.view=e.render(r,o,r),this.view.sourceLifetime=le.coupled}static forCustomElement(e,r=!1){let o=e.$fastController;if(o!==void 0&&!r)return o;let n=R.getForInstance(e);if(n===void 0)throw S.error(b.missingElementDefinition);return m.getNotifier(n).subscribe({handleChange:()=>{t.forCustomElement(e,!0),e.$fastController.connect()}},"template"),m.getNotifier(n).subscribe({handleChange:()=>{t.forCustomElement(e,!0),e.$fastController.connect()}},"shadowOptions"),e.$fastController=new ao(e,n)}static setStrategy(e){ao=e}static installHydrationHook(e){t.hydrationHook=e}};se.hydrationHook=null;$(se);se.setStrategy(se);function vt(t){var e;return"adoptedStyleSheets"in t?t:(e=mt(t))!==null&&e!==void 0?e:t.getRootNode()}var bt=class t{constructor(e){let r=t.styleSheetCache;this.sheets=e.map(o=>{if(o instanceof CSSStyleSheet)return o;let n=r.get(o);return n===void 0&&(n=new CSSStyleSheet,n.replaceSync(o),r.set(o,n)),n})}addStylesTo(e){so(vt(e),this.sheets)}removeStylesFrom(e){co(vt(e),this.sheets)}};bt.styleSheetCache=new Map;var ki=0,Pi=()=>`fast-${++ki}`;function io(t){return t===document?document.body:t}var ar=class{constructor(e){this.styles=e,this.styleClass=Pi()}addStylesTo(e){e=io(vt(e));let r=this.styles,o=this.styleClass;for(let n=0;n<r.length;n++){let a=document.createElement("style");a.innerHTML=r[n],a.className=o,e.append(a)}}removeStylesFrom(e){e=io(vt(e));let r=e.querySelectorAll(`.${this.styleClass}`);for(let o=0,n=r.length;o<n;++o)e.removeChild(r[o])}},so=(t,e)=>{t.adoptedStyleSheets=[...t.adoptedStyleSheets,...e]},co=(t,e)=>{t.adoptedStyleSheets=t.adoptedStyleSheets.filter(r=>e.indexOf(r)===-1)};if(H.supportsAdoptedStyleSheets){try{document.adoptedStyleSheets.push(),document.adoptedStyleSheets.splice(),so=(t,e)=>{t.adoptedStyleSheets.push(...e)},co=(t,e)=>{for(let r of e){let o=t.adoptedStyleSheets.indexOf(r);o!==-1&&t.adoptedStyleSheets.splice(o,1)}}}catch{}H.setDefaultStrategy(bt)}else H.setDefaultStrategy(ar);function uo(t){let e=class extends t{constructor(){super(),se.forCustomElement(this)}$emit(r,o,n){return this.$fastController.emit(r,o,n)}connectedCallback(){this.$fastController.connect()}disconnectedCallback(){this.$fastController.disconnect()}attributeChangedCallback(r,o,n){this.$fastController.onAttributeChangedCallback(r,o,n)}};return R.registerBaseType(e),e}function Ni(t){return typeof t?.then=="function"}function Fi(t,e,r){return Array.isArray(e)&&(r=e,e=void 0),(j(t)?R.compose(t,e):R.compose(this,t)).then(n=>{tr(n,n.registry,r);let a=rr(n);return Ni(a)?a.then(()=>n.define().type):n.define().type})}function wi(t){return uo(t)}var z=Object.assign(uo(HTMLElement),{from:wi,define:Fi});var ir=ye(),lr=Object.freeze({getForInstance:ir.getForInstance,getByType:ir.getByType,define(t){return ir.register({type:t}),t}});function po(t,e){let r=[],o="";for(let n=0,a=t.length-1;n<a;++n){o+=t[n];let i=e[n];lr.getForInstance(i)!==void 0&&(i=i.createCSS()),i instanceof H||i instanceof CSSStyleSheet?(o.trim()!==""&&(r.push(o),o=""),r.push(i)):o+=i}return o+=t[t.length-1],o.trim()!==""&&r.push(o),r}var y=((t,...e)=>new H(po(t,e))),Bt=class{constructor(e){this.value=e.length===0?"":e.length===1?e[0]:new H(e)}createCSS(){return this.value}};lr.define(Bt);y.partial=(t,...e)=>new Bt(po(t,e));var sr=`fast-${Math.random().toString(36).substring(2,8)}`,xt=`${sr}{`,Xe=`}${sr}`,Ti=Xe.length,Ai=0,Ue=()=>`${sr}-${++Ai}`,St=Object.freeze({interpolation:t=>`${xt}${t}${Xe}`,attribute:t=>`${Ue()}="${xt}${t}${Xe}"`,comment:t=>`<!--${xt}${t}${Xe}-->`}),qe=Object.freeze({parse(t,e){let r=t.split(xt);if(r.length===1)return null;let o=[];for(let n=0,a=r.length;n<a;++n){let i=r[n],s=i.indexOf(Xe),u;if(s===-1)u=i;else{let c=i.substring(0,s);o.push(e[c]),u=i.substring(s+Ti)}u!==""&&o.push(u)}return o}});var cr=ye(),T=Object.freeze({getForInstance:cr.getForInstance,getByType:cr.getByType,define(t,e){return e=e||{},e.type=t,cr.register(e),t},assignAspect(t,e){if(!e){t.aspectType=P.content;return}switch(t.sourceAspect=e,e[0]){case":":t.targetAspect=e.substring(1),t.aspectType=t.targetAspect==="classList"?P.tokenList:P.property;break;case"?":t.targetAspect=e.substring(1),t.aspectType=P.booleanAttribute;break;case"@":t.targetAspect=e.substring(1),t.aspectType=P.event;break;default:t.targetAspect=e,t.aspectType=P.attribute;break}}});var fe=class{constructor(e){this.options=e}createHTML(e){return St.attribute(e(this))}createBehavior(){return this}};$(fe);var yt=class extends fe{get id(){return this._id}set id(e){this._id=e,this._controllerProperty=`${e}-c`}bind(e){let r=e.targets[this.targetNodeId];r[this._controllerProperty]=e,this.updateTarget(e.source,this.computeNodes(r)),this.observe(r),e.onUnbind(this)}unbind(e){let r=e.targets[this.targetNodeId];this.updateTarget(e.source,jr),this.disconnect(r),r[this._controllerProperty]=null}getSource(e){return e[this._controllerProperty].source}updateTarget(e,r){e[this.options.property]=r}computeNodes(e){let r=this.getNodes(e);return"filter"in this.options&&(r=r.filter(this.options.filter)),r}};var go=/fe-b\$\$start\$\$(\d+)\$\$(.+)\$\$fe-b/,Ci=/fe-b\$\$end\$\$(\d+)\$\$(.+)\$\$fe-b/,$i=/fe-repeat\$\$start\$\$(\d+)\$\$fe-repeat/,Hi=/fe-repeat\$\$end\$\$(\d+)\$\$fe-repeat/,Di=/^(?:.{0,1000})fe-eb\$\$start\$\$(.+?)\$\$fe-eb/,Li=/fe-eb\$\$end\$\$(.{0,1000})\$\$fe-eb(?:.{0,1000})$/;function ho(t){return t&&t.nodeType===Node.COMMENT_NODE}var I=Object.freeze({attributeMarkerName:"data-fe",legacyAttributeMarkerName:"data-fe-b",legacyCompactAttributeMarkerName:"data-fe-c",contentBindingStartMarker(){return"fe:b"},contentBindingEndMarker(){return"fe:/b"},repeatStartMarker(){return"fe:r"},repeatEndMarker(){return"fe:/r"},elementBoundaryStartMarker(){return"fe:e"},elementBoundaryEndMarker(){return"fe:/e"},isContentBindingStartMarker(t){return t==="fe:b"||go.test(t)},isContentBindingEndMarker(t){return t==="fe:/b"||Ci.test(t)},isRepeatViewStartMarker(t){return t==="fe:r"||$i.test(t)},isRepeatViewEndMarker(t){return t==="fe:/r"||Hi.test(t)},isElementBoundaryStartMarker(t){return ho(t)&&(t.data==="fe:e"||Di.test(t.data))},isElementBoundaryEndMarker(t){return ho(t)&&(t.data==="fe:/e"||Li.test(t.data))},parseAttributeBindingCount(t){let e=t.getAttribute(this.attributeMarkerName);if(e===null)return null;let r=e.trim();if(!/^\d+$/.test(r))throw S.error(b.invalidHydrationAttributeMarker,{value:e});let o=parseInt(r,10);if(o<1)throw S.error(b.invalidHydrationAttributeMarker,{value:e});return o},parseLegacyAttributeBindingIndices(t){let e=[],r=t.getAttribute(this.legacyAttributeMarkerName);if(r!==null)for(let a of r.trim().split(/\s+/)){if(a==="")continue;let i=Number(a);if(!Number.isInteger(i)||i<0)throw S.error(b.invalidHydrationAttributeMarker,{value:r});e.push(i)}let o=`${this.legacyAttributeMarkerName}-`,n=`${this.legacyCompactAttributeMarkerName}-`;for(let a of t.getAttributeNames())if(a.startsWith(o)){let i=Number(a.slice(o.length));if(!Number.isInteger(i)||i<0)throw S.error(b.invalidHydrationAttributeMarker,{value:a});e.push(i)}else if(a.startsWith(n)){let[i,s]=a.slice(n.length).split("-").map(u=>Number(u));if(!Number.isInteger(i)||!Number.isInteger(s)||i<0||s<1)throw S.error(b.invalidHydrationAttributeMarker,{value:a});for(let u=0;u<s;u++)e.push(i+u)}return e.length===0?null:e},removeLegacyAttributeBindingMarkers(t){t.removeAttribute(this.legacyAttributeMarkerName);for(let e of t.getAttributeNames())(e.startsWith(`${this.legacyAttributeMarkerName}-`)||e.startsWith(`${this.legacyCompactAttributeMarkerName}-`))&&t.removeAttribute(e)},parseLegacyContentBindingStartIndex(t){return Ii(go,t)}});function Ii(t,e){let r=t.exec(e);return r===null?null:Number(r[1])}var Ye=Symbol.for("fe-hydration");function kt(t){return t[Ye]===Ye}var fo="unknown";function mo(t,e){let r=e?`: ${e}`:"";return`Hydration mismatch in <${t}>${r}. Install hydrationDebugger() from "@microsoft/fast-element/hydration.js" and pass it as enableHydration({ debugger: hydrationDebugger() }) for an "Expected / Received" report including the SSR HTML snippet.`}var vo="content following `<!--fe:b-->` content binding marker",bo="matching `<!--fe:/b-->` content binding close marker",Bo="matching `<!--fe:/e-->` element boundary close marker";function dr(t){return`no more attribute bindings (template defines ${t})`}function xo(t){return`no more content bindings (template defines ${t})`}function So(t,e){let r=(t??fo).toLowerCase();return mo(r,e)}var Oi={formatBindingMismatch(t,e,r,o){return{message:So(o,void 0)}},formatStructuralError(t,e,r){return{message:So(e,r)}}},Mi=Oi;function K(){return Mi}function J(t){var e;return t?(e=t.getRootNode().host)===null||e===void 0?void 0:e.nodeName:void 0}var W=class extends Error{constructor(e,r,o,n,a){super(e),this.factories=r,this.node=o,this.expected=n,this.received=a}};function ur(t){return t.nodeType===Node.COMMENT_NODE}function yo(t){return t.nodeType===Node.TEXT_NODE}function pr(t,e){let r=document.createRange();return r.setStart(t,0),r.setEnd(e,ur(e)||yo(e)?e.data.length:e.childNodes.length),r}function ko(t,e,r){let o=pr(t,e),n=o.commonAncestorContainer,a=document.createTreeWalker(n,NodeFilter.SHOW_ELEMENT+NodeFilter.SHOW_COMMENT+NodeFilter.SHOW_TEXT,{acceptNode(p){return o.comparePoint(p,0)===0?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT}}),i={},s={},u=Ei(r),c=u,l=a.currentNode=t;for(;l!==null;){switch(l.nodeType){case Node.ELEMENT_NODE:{let p=l,f=I.parseLegacyAttributeBindingIndices(p);if(f!==null){for(let N of f){let V=N+u,ae=r[V];if(!ae){let Ve=dr(r.length),Ut=K().formatStructuralError(l,J(l),Ve);throw new W(Ut.message,r,p,Ut.expected,Ut.received)}we(ae,l,i),c=Math.max(c,V+1)}I.removeLegacyAttributeBindingMarkers(p);break}let x=I.parseAttributeBindingCount(p);if(x!==null){for(let N=0;N<x;N++){let V=r[c++];if(!V){let ae=dr(r.length),Ve=K().formatStructuralError(l,J(l),ae);throw new W(Ve.message,r,l,Ve.expected,Ve.received)}we(V,l,i)}p.removeAttribute(I.attributeMarkerName)}break}case Node.COMMENT_NODE:{let p=l.data;if(I.isElementBoundaryStartMarker(l))l.data="",zi(a,r,l);else if(I.isContentBindingStartMarker(p)){let f=I.parseLegacyContentBindingStartIndex(p),x=f===null?c++:f+u,N=r[x];if(c=Math.max(c,x+1),!N){let V=xo(r.length),ae=K().formatStructuralError(l,J(l),V);throw new W(ae.message,r,l,ae.expected,ae.received)}Ri(l,a,N,r,i,s)}break}}l=a.nextNode()}return o.detach(),{targets:i,boundaries:s}}function Ri(t,e,r,o,n,a){let i=[],s=e.nextSibling();if(t.data="",s===null){let l=vo,p=K().formatStructuralError(t,J(t),l);throw new W(p.message,o,t,p.expected,p.received)}let u=s,c=0;for(;s!==null;){if(ur(s)){if(I.isContentBindingStartMarker(s.data))c++;else if(I.isContentBindingEndMarker(s.data)){if(c===0)break;c--}}i.push(s),s=e.nextSibling()}if(s===null){let l=bo,p=K().formatStructuralError(t,J(t),l);throw new W(p.message,o,t,p.expected,p.received)}if(s.data="",i.length===1&&yo(i[0]))we(r,i[0],n);else{s!==u&&s.previousSibling!==null&&(a[r.targetNodeId]={first:u,last:s.previousSibling});let l=s.parentNode.insertBefore(document.createTextNode(""),s);we(r,l,n)}}function zi(t,e,r){let o=0,n=t.nextSibling();for(;n!==null;){if(ur(n)){if(I.isElementBoundaryStartMarker(n))n.data="",o++;else if(I.isElementBoundaryEndMarker(n)){if(o===0){n.data="";return}n.data="",o--}}n=t.nextSibling()}let a=Bo,i=K().formatStructuralError(r,J(r),a);throw new W(i.message,e,r,i.expected,i.received)}function Ei(t){let e=0;for(let r=0,o=t.length;r<o&&t[r].targetNodeId==="h";++r)e++;return e}function we(t,e,r){if(t.targetNodeId===void 0)throw new Error("Factory could not be target to the node");r[t.targetNodeId]=e}function Te(t,e){let r=t.parentNode,o=t,n;for(;o!==e;){if(n=o.nextSibling,!n)throw new Error(`Unmatched first/last child inside "${e.getRootNode().host.nodeName}".`);r.removeChild(o),o=n}r.removeChild(e)}var Ke=class{constructor(){this.index=0,this.length=0}get event(){return q.getEvent()}get isEven(){return this.index%2===0}get isOdd(){return this.index%2!==0}get isFirst(){return this.index===0}get isInMiddle(){return!this.isFirst&&!this.isLast}get isLast(){return this.index===this.length-1}eventDetail(){return this.event.detail}eventTarget(){return this.event.target}},me=class extends Ke{constructor(e,r,o){super(),this.fragment=e,this.factories=r,this.targets=o,this.behaviors=null,this.unbindables=[],this.source=null,this.isBound=!1,this.sourceLifetime=le.unknown,this._skipAttrUpdates=!1,this.isPrerendered=Promise.resolve(!1),this.isHydrated=Promise.resolve(!1),this.context=this,this.firstChild=e.firstChild,this.lastChild=e.lastChild}appendTo(e){e.appendChild(this.fragment)}insertBefore(e){if(this.fragment.hasChildNodes())e.parentNode.insertBefore(this.fragment,e);else{let r=this.lastChild;if(e.previousSibling===r)return;let o=e.parentNode,n=this.firstChild,a;for(;n!==r;)a=n.nextSibling,o.insertBefore(n,e),n=a;o.insertBefore(r,e)}}remove(){let e=this.fragment,r=this.lastChild,o=this.firstChild,n;for(;o!==r;)n=o.nextSibling,e.appendChild(o),o=n;e.appendChild(r)}dispose(){Te(this.firstChild,this.lastChild),this.unbind()}onUnbind(e){this.unbindables.push(e)}bind(e,r=this){if(this.source===e&&this.context===r)return;let o=this.behaviors;if(o===null){this.source=e,this.context=r,this.behaviors=o=new Array(this.factories.length);let n=this.factories;for(let a=0,i=n.length;a<i;++a){let s=n[a].createBehavior();s.bind(this),o[a]=s}}else{this.source!==null&&this.evaluateUnbindables(),this.isBound=!1,this.source=e,this.context=r;for(let n=0,a=o.length;n<a;++n)o[n].bind(this)}this.isBound=!0}unbind(){!this.isBound||this.source===null||(this.evaluateUnbindables(),this.source=null,this.context=this,this.isBound=!1)}evaluateUnbindables(){let e=this.unbindables;for(let r=0,o=e.length;r<o;++r)e[r].unbind(this);e.length=0}static disposeContiguousBatch(e){if(e.length!==0){Te(e[0].firstChild,e[e.length-1].lastChild);for(let r=0,o=e.length;r<o;++r)e[r].unbind()}}};$(me);m.defineProperty(me.prototype,"index");m.defineProperty(me.prototype,"length");var Po,ve={unhydrated:"unhydrated",hydrating:"hydrating",hydrated:"hydrated"},gr=class extends Error{constructor(e,r,o,n,a,i){super(e),this.factory=r,this.fragment=o,this.templateString=n,this.expected=a,this.received=i}},hr=class extends Ke{get hydrationStage(){return this._hydrationStage}get targets(){return this._targets}get bindingViewBoundaries(){return this._bindingViewBoundaries}constructor(e,r,o,n){super(),this.firstChild=e,this.lastChild=r,this.sourceTemplate=o,this.hostBindingTarget=n,this[Po]=Ye,this.context=this,this.source=null,this.isBound=!1,this.sourceLifetime=le.unknown,this.unbindables=[],this.fragment=null,this.behaviors=null,this._hydrationStage=ve.unhydrated,this._bindingViewBoundaries={},this._targets={},this.factories=o.compile().factories}insertBefore(e){if(this.fragment!==null)if(this.fragment.hasChildNodes())e.parentNode.insertBefore(this.fragment,e);else{let r=this.lastChild;if(e.previousSibling===r)return;let o=e.parentNode,n=this.firstChild,a;for(;n!==r;)a=n.nextSibling,o.insertBefore(n,e),n=a;o.insertBefore(r,e)}}appendTo(e){this.fragment!==null&&e.appendChild(this.fragment)}remove(){let e=this.fragment||(this.fragment=document.createDocumentFragment()),r=this.lastChild,o=this.firstChild,n;for(;o!==r;){if(n=o.nextSibling,!n)throw new Error(`Unmatched first/last child inside "${r.getRootNode().host.nodeName}".`);e.appendChild(o),o=n}e.appendChild(r)}bind(e,r=this){if(this.source===e&&this.context===r)return;this.hydrationStage!==ve.hydrated&&(this._hydrationStage=ve.hydrating);let o=this.behaviors;if(o===null){this.source=e,this.context=r;try{let{targets:a,boundaries:i}=ko(this.firstChild,this.lastChild,this.factories);this._targets=a,this._bindingViewBoundaries=i}catch(a){if(a instanceof W){let i=this.sourceTemplate.html;typeof i!="string"&&(i=i.innerHTML),a.templateString=i}throw a}this.behaviors=o=new Array(this.factories.length);let n=this.factories;for(let a=0,i=n.length;a<i;++a){let s=n[a];if(s.targetNodeId==="h"&&this.hostBindingTarget&&we(s,this.hostBindingTarget,this._targets),s.targetNodeId in this.targets){let u=s.createBehavior();u.bind(this),o[a]=u}else{let u=this.sourceTemplate.html;typeof u!="string"&&(u=u.innerHTML);let c=pr(this.firstChild,this.lastChild).cloneContents(),l=K().formatBindingMismatch(s,this.firstChild,this.lastChild,J(this.firstChild));throw new gr(l.message,s,c,u,l.expected,l.received)}}}else{this.source!==null&&this.evaluateUnbindables(),this.isBound=!1,this.source=e,this.context=r;for(let n=0,a=o.length;n<a;++n)o[n].bind(this)}this.isBound=!0,this._hydrationStage=ve.hydrated}unbind(){!this.isBound||this.source===null||(this.evaluateUnbindables(),this.source=null,this.context=this,this.isBound=!1)}dispose(){Te(this.firstChild,this.lastChild),this.unbind()}onUnbind(e){this.unbindables.push(e)}evaluateUnbindables(){let e=this.unbindables;for(let r=0,o=e.length;r<o;++r)e[r].unbind(this);e.length=0}};Po=Ye;$(hr);function _i(t){return t.create!==void 0}function Vi(t,e,r,o){if(r==null&&(r=""),_i(r)){t.textContent="";let n=t.$fastView;if(n===void 0)if(kt(o)&&kt(r)&&o.bindingViewBoundaries[this.targetNodeId]!==void 0&&o.hydrationStage!==ve.hydrated){let a=o.bindingViewBoundaries[this.targetNodeId];n=r.hydrate(a.first,a.last)}else n=r.create();else t.$fastTemplate!==r&&(n.isComposed&&(n.remove(),n.unbind()),n=r.create());n.isComposed?n.needsBindOnly&&(n.needsBindOnly=!1,n.bind(o.source,o.context)):(n.isComposed=!0,n.bind(o.source,o.context),n.insertBefore(t),t.$fastView=n,t.$fastTemplate=r)}else{let n=t.$fastView;if(n!==void 0&&n.isComposed&&(n.isComposed=!1,n.remove(),n.needsBindOnly?n.needsBindOnly=!1:n.unbind()),n===void 0&&kt(o)&&o.hydrationStage!==ve.hydrated){let a=o.bindingViewBoundaries[this.targetNodeId];a!==void 0&&(Te(a.first,a.last),delete o.bindingViewBoundaries[this.targetNodeId])}t.textContent=r}}function ji(t,e,r){var o;let n=`${this.id}-t`,a=(o=t[n])!==null&&o!==void 0?o:t[n]={v:0,cv:Object.create(null)},i=a.cv,s=a.v,u=t[e];if(r!=null&&r.length){let c=r.split(/\s+/);for(let l=0,p=c.length;l<p;++l){let f=c[l];f!==""&&(i[f]=s,u.add(f))}}if(a.v=s+1,s!==0){s-=1;for(let c in i)i[c]===s&&u.remove(c)}}var Gi={[P.attribute]:Y.setAttribute,[P.booleanAttribute]:Y.setBooleanAttribute,[P.property]:(t,e,r)=>t[e]=r,[P.content]:Vi,[P.tokenList]:ji,[P.event]:()=>{}},X=class{constructor(e){this.updateTarget=null,this.aspectType=P.content,this.dataBinding=e}createHTML(e){return St.interpolation(e(this))}createBehavior(){var e;if(this.updateTarget===null){let r=Gi[this.aspectType],o=(e=this.dataBinding.policy)!==null&&e!==void 0?e:this.policy;if(!r)throw S.error(b.unsupportedBindingBehavior);this.data=`${this.id}-d`,this.updateTarget=o.protect(this.targetTagName,this.aspectType,this.targetAspect,r)}return this}bind(e){var r;let o=e.targets[this.targetNodeId];switch(this.aspectType){case P.event:o[this.data]=e,o.addEventListener(this.targetAspect,this,this.dataBinding.options);break;case P.content:e.onUnbind(this);default:{let n=(r=o[this.data])!==null&&r!==void 0?r:o[this.data]=this.dataBinding.createObserver(this,this);n.target=o,n.controller=e;let a=n.bind(e);if(e._skipAttrUpdates&&(this.aspectType===P.attribute||this.aspectType===P.booleanAttribute))break;this.updateTarget(o,this.targetAspect,a,e);break}}}unbind(e){let o=e.targets[this.targetNodeId].$fastView;o!==void 0&&o.isComposed&&(o.unbind(),o.needsBindOnly=!0)}handleEvent(e){let r=e.currentTarget[this.data];if(r.isBound){q.setEvent(e);let o=this.dataBinding.evaluate(r.source,r.context);q.setEvent(null),o!==!0&&e.preventDefault()}}handleChange(e,r){let o=r.controller;if(!o.isBound)return;let n=r.target;this.updateTarget(n,this.targetAspect,r.bind(o),o)}};T.define(X,{aspected:!0});var To=(t,e)=>`${t}.${e}`,No={},U={index:0,node:null};function Fo(t){t.startsWith("fast-")||S.warn(b.hostBindingWithoutHost,{name:t})}var Wi=new Proxy(document.createElement("div"),{get(t,e){Fo(e);let r=Reflect.get(t,e);return j(r)?r.bind(t):r},set(t,e,r){return Fo(e),Reflect.set(t,e,r)}}),fr=class{constructor(e,r,o){this.fragment=e,this.directives=r,this.policy=o,this.proto=null,this.nodeIds=new Set,this.descriptors={},this.factories=[]}addFactory(e,r,o,n,a){var i,s;this.nodeIds.has(o)||(this.nodeIds.add(o),this.addTargetDescriptor(r,o,n)),e.id=(i=e.id)!==null&&i!==void 0?i:Ue(),e.targetNodeId=o,e.targetTagName=a,e.policy=(s=e.policy)!==null&&s!==void 0?s:this.policy,this.factories.push(e)}freeze(){return this.proto=Object.create(null,this.descriptors),this}addTargetDescriptor(e,r,o){let n=this.descriptors;if(r==="r"||r==="h"||n[r])return;if(!n[e]){let i=e.lastIndexOf("."),s=e.substring(0,i),u=parseInt(e.substring(i+1),10);this.addTargetDescriptor(s,e,u)}let a=No[r];if(!a){let i=`_${r}`;No[r]=a={get(){var s;return(s=this[i])!==null&&s!==void 0?s:this[i]=this[e].childNodes[o]}}}n[r]=a}createView(e){let r=this.fragment.cloneNode(!0),o=Object.create(this.proto);o.r=r,o.h=e??Wi;for(let n of this.nodeIds)Reflect.get(o,n);return new me(r,this.factories,o)}};function Ao(t,e,r,o,n,a=!1){let i=r.attributes,s=t.directives;for(let u=0,c=i.length;u<c;++u){let l=i[u],p=l.value,f=qe.parse(p,s),x=null;f===null?a&&(x=new X(dt(()=>p,t.policy)),T.assignAspect(x,l.name)):x=Pt.aggregate(f,t.policy),x!==null&&(r.removeAttributeNode(l),u--,c--,t.addFactory(x,e,o,n,r.tagName))}}function Xi(t,e,r,o,n){let a=qe.parse(e.textContent,t.directives);if(a===null)return U.node=e.nextSibling,U.index=n+1,U;let i,s=i=e;for(let u=0,c=a.length;u<c;++u){let l=a[u];u!==0&&(n++,o=To(r,n),i=s.parentNode.insertBefore(document.createTextNode(""),s.nextSibling)),C(l)?i.textContent=l:(i.textContent=" ",T.assignAspect(l),t.addFactory(l,r,o,n,null)),s=i}return U.index=n+1,U.node=s.nextSibling,U}function Co(t,e,r){let o=0,n=e.firstChild;for(;n;){let a=Ui(t,r,n,o);n=a.node,o=a.index}}function Ui(t,e,r,o){let n=To(e,o);switch(r.nodeType){case 1:Ao(t,e,r,n,o),Co(t,r,n);break;case 3:return Xi(t,r,e,n,o);case 8:{let a=qe.parse(r.data,t.directives);a!==null&&t.addFactory(Pt.aggregate(a),e,n,o,null);break}}return U.index=o+1,U.node=r.nextSibling,U}function qi(t,e){return t&&t.nodeType===8&&qe.parse(t.data,e)!==null}var wo="TEMPLATE",Pt={compile(t,e,r=Y.policy){let o;if(C(t)){o=document.createElement(wo),o.innerHTML=r.createHTML(t);let i=o.content.firstElementChild;i!==null&&i.tagName===wo&&(o=i)}else o=t;!o.content.firstChild&&!o.content.lastChild&&o.content.appendChild(document.createComment(""));let n=document.adoptNode(o.content),a=new fr(n,e,r);return Ao(a,"",o,"h",0,!0),(qi(n.firstChild,e)||n.childNodes.length===1&&Object.keys(e).length>0)&&n.insertBefore(document.createComment(""),n.firstChild),Co(a,n,"r"),U.node=null,a.freeze()},setDefaultStrategy(t){this.compile=t},aggregate(t,e=Y.policy){if(t.length===1)return t[0];let r,o=!1,n,a=t.length,i=t.map(c=>C(c)?()=>c:(r=c.sourceAspect||r,o=o||c.dataBinding.isVolatile,n=n||c.dataBinding.policy,c.dataBinding.evaluate)),s=(c,l)=>{let p="";for(let f=0;f<a;++f)p+=i[f](c,l);return p},u=new X(ut(s,n??e,o));return T.assignAspect(u,r),u}};var Je=class extends fe{bind(e){e.source[this.options]=e.targets[this.targetNodeId]}};T.define(Je);var Ae=t=>new Je(t);var Yi=/([ \x09\x0a\x0c\x0d])([^\0-\x1F\x7F-\x9F "'>=/]+)([ \x09\x0a\x0c\x0d]*=[ \x09\x0a\x0c\x0d]*(?:[^ \x09\x0a\x0c\x0d"'`<>=]*|"[^"]*|'[^']*))$/,Ki=Object.create(null),E=class{constructor(e,r=Ki){this.html=e,this.factories=r}createHTML(e){let r=this.factories;for(let o in r)e(r[o]);return this.html}};E.empty=new E("");T.define(E);function Ji(t,e,r,o=T.getForInstance(t)){if(o.aspected){let n=Yi.exec(e);n!==null&&T.assignAspect(t,n[2])}return t.createHTML(r)}var Qe=class t{constructor(e,r={},o){this.policy=o,this.result=null,this.html=e,this.factories=r}compile(){return this.result===null&&(this.result=Pt.compile(this.html,this.factories,this.policy)),this.result}inline(){return new E(C(this.html)?this.html:this.html.innerHTML,this.factories)}withPolicy(e){if(this.result)throw S.error(b.cannotSetTemplatePolicyAfterCompilation);if(this.policy)throw S.error(b.onlySetTemplatePolicyOnce);return this.policy=e,this}render(e,r,o){let n=this.create(o);return n.bind(e),n.appendTo(r),n}create(e){return this.compile().createView(e)}static create(e,r,o){let n="",a=Object.create(null),i=s=>{var u;let c=(u=s.id)!==null&&u!==void 0?u:s.id=Ue();return a[c]=s,c};for(let s=0,u=e.length-1;s<u;++s){let c=e[s],l=r[s],p;if(n+=c,j(l))l=new X(ut(l));else if(l instanceof ie)l=new X(l);else if(!(p=T.getForInstance(l))){let f=l;l=new X(dt(()=>f))}n+=Ji(l,c,i,p)}return new t(n+e[e.length-1],a,o)}};$(Qe);var A=((t,...e)=>{if(Array.isArray(t)&&Array.isArray(t.raw))return Qe.create(t,e);throw S.error(b.directCallToHTMLTagNotAllowed)});A.partial=t=>new E(t);var $o="slotchange",Ze=class extends yt{observe(e){e.addEventListener($o,this)}disconnect(e){e.removeEventListener($o,this)}getNodes(e){return e.assignedNodes(this.options)}handleEvent(e){let r=e.currentTarget;this.updateTarget(this.getSource(r),this.computeNodes(r))}};T.define(Ze);function mr(t){return C(t)&&(t={property:t}),new Ze(t)}function et(t){return t?typeof t=="string"?new E(t):"inline"in t?t.inline():t:E.empty}var ce=class{};function Ce(t){return A` <slot name="end" ${Ae("end")}>${et(t.end)}</slot> `.inline()}function $e(t){return A` <slot name="start" ${Ae("start")}>${et(t.start)}</slot> `.inline()}function He(t,...e){let r=Ne.locate(t);e.forEach(o=>{Object.getOwnPropertyNames(o.prototype).forEach(a=>{a!=="constructor"&&Object.defineProperty(t.prototype,a,Object.getOwnPropertyDescriptor(o.prototype,a))}),Ne.locate(o).forEach(a=>r.push(a))})}var k=Object.freeze({prefix:"fluent",shadowRootMode:"open",registry:globalThis.customElements});var Qi=":host([hidden]){display:none}";function De(t){return`${Qi}:host{display:${t}}`}var Le="var(--colorNeutralForeground1)",Ho="var(--colorNeutralForeground1Hover)",Do="var(--colorNeutralForeground1Pressed)";var vr="var(--colorNeutralForeground2)",Lo="var(--colorNeutralForeground2Hover)",Io="var(--colorNeutralForeground2Pressed)";var br="var(--colorNeutralForeground2BrandHover)",Br="var(--colorNeutralForeground2BrandPressed)";var _="var(--colorNeutralForeground3)";var Oo="var(--colorNeutralForegroundDisabled)";var Q="var(--colorNeutralForegroundOnBrand)",Mo="var(--colorNeutralForegroundInverted)";var Ro="var(--colorNeutralForegroundStaticInverted)";var xr="var(--colorBrandForeground1)",zo="var(--colorBrandForeground2)";var Eo="var(--colorNeutralForeground1Static)";var be="var(--colorNeutralBackground1)",_o="var(--colorNeutralBackground1Hover)",Vo="var(--colorNeutralBackground1Pressed)";var jo="var(--colorNeutralBackground3)";var Go="var(--colorNeutralBackground4)";var Wo="var(--colorNeutralBackground5)";var Nt="var(--colorNeutralBackground6)";var Xo="var(--colorSubtleBackground)",Uo="var(--colorSubtleBackgroundHover)",qo="var(--colorSubtleBackgroundPressed)";var de="var(--colorTransparentBackground)",Sr="var(--colorTransparentBackgroundHover)",yr="var(--colorTransparentBackgroundPressed)";var Yo="var(--colorNeutralBackgroundDisabled)";var Ft="var(--colorBrandBackground)",Ko="var(--colorBrandBackgroundHover)",Jo="var(--colorBrandBackgroundPressed)";var Qo="var(--colorCompoundBrandBackground)";var Zo="var(--colorBrandBackground2)";var en="var(--colorNeutralStrokeAccessible)";var wt="var(--colorNeutralStroke1)",tn="var(--colorNeutralStroke1Hover)",rn="var(--colorNeutralStroke1Pressed)";var Tt="var(--colorNeutralStroke2)";var on="var(--colorBrandStroke2)";var nn="var(--colorNeutralStrokeDisabled)";var Ie="var(--colorTransparentStroke)";var kr="var(--colorStrokeFocus2)";var At="var(--colorPaletteRedBackground1)";var Ct="var(--colorPaletteRedBackground3)";var $t="var(--colorPaletteRedBorder1)";var an="var(--colorPaletteRedForeground1)";var Pr="var(--colorPaletteRedForeground3)";var Ht="var(--colorPaletteGreenBackground1)";var Dt="var(--colorPaletteGreenBackground3)";var ln="var(--colorPaletteGreenBorder1)",sn="var(--colorPaletteGreenBorder2)",cn="var(--colorPaletteGreenForeground1)",dn="var(--colorPaletteGreenForeground2)",un="var(--colorPaletteGreenForeground3)";var Lt="var(--colorPaletteDarkOrangeBackground1)";var It="var(--colorPaletteDarkOrangeBackground3)";var Ot="var(--colorPaletteDarkOrangeBorder1)";var pn="var(--colorPaletteDarkOrangeForeground1)";var Nr="var(--colorPaletteDarkOrangeForeground3)",gn="var(--colorPaletteYellowBackground1)";var hn="var(--colorPaletteYellowBackground3)";var fn="var(--colorPaletteYellowBorder1)";var Mt="var(--colorPaletteYellowForeground2)";var Oe="var(--borderRadiusNone)",Rt="var(--borderRadiusSmall)",ue="var(--borderRadiusMedium)",mn="var(--borderRadiusLarge)";var zt="var(--borderRadiusCircular)",Me="var(--fontFamilyBase)";var vn="var(--fontSizeBase100)",pe="var(--fontSizeBase200)",bn="var(--fontSizeBase300)",Bn="var(--fontSizeBase400)";var xn="var(--fontWeightRegular)";var Et="var(--fontWeightSemibold)";var Sn="var(--lineHeightBase100)",ge="var(--lineHeightBase200)",yn="var(--lineHeightBase300)",kn="var(--lineHeightBase400)";var Pn="var(--shadow2)",Nn="var(--shadow4)";var _t="var(--strokeWidthThin)",Fn="var(--strokeWidthThick)";var Re="var(--spacingHorizontalXXS)",tt="var(--spacingHorizontalXS)",Vt="var(--spacingHorizontalSNudge)",ze="var(--spacingHorizontalS)";var rt="var(--spacingHorizontalM)",wn="var(--spacingHorizontalL)";var Tn="var(--spacingVerticalS)",jt="var(--spacingVerticalMNudge)";var An="var(--durationFaster)";var Cn="var(--curveEasyEase)";var $n={primary:"primary",outline:"outline",subtle:"subtle",transparent:"transparent"},Hn={circular:"circular",rounded:"rounded",square:"square"},Dn={small:"small",medium:"medium",large:"large"},ot={submit:"submit",reset:"reset",button:"button"};var Ln=`${k.prefix}-button`;var In=$n,On=Hn,Mn=Dn;var Rn={download:"download",href:"href",hreflang:"hreflang",ping:"ping",referrerpolicy:"referrerpolicy",rel:"rel",target:"target",type:"type"},zn=`${k.prefix}-anchor-button`;var O=class extends z{constructor(){super(),this.isMac=navigator.userAgent.includes("Mac"),this.elementInternals=this.attachInternals(),this.internalProxyAnchor=this.createProxyElement(),this.elementInternals.role="link"}connectedCallback(){super.connectedCallback(),this.tabIndex=Number(this.getAttribute("tabindex")??0)<0?-1:0,m.getNotifier(this).subscribe(this),Object.keys(this.$fastController.definition.attributeLookup).forEach(e=>{this.handleChange(this,e)}),this.append(this.internalProxyAnchor)}disconnectedCallback(){super.disconnectedCallback(),m.getNotifier(this).unsubscribe(this)}handleChange(e,r){if(r in Rn){let o=this.$fastController.definition.attributeLookup[r]?.attribute;o&&this.handleProxyAttributeChange(o,this[r])}}clickHandler(e){if(e.composedPath()[0]===this.internalProxyAnchor)return e.stopImmediatePropagation(),!0;if(this.href){let r=e.ctrlKey||e.metaKey;this.handleNavigation(r)}return!0}keydownHandler(e){if(this.href&&e.key==="Enter"){let r=this.isMac&&e.metaKey||e.ctrlKey;this.handleNavigation(r);return}return!0}handleNavigation(e){e?window.open(this.href,"_blank"):this.internalProxyAnchor.click()}handleProxyAttributeChange(e,r){r?this.internalProxyAnchor.setAttribute(e,r):this.internalProxyAnchor.removeAttribute(e)}createProxyElement(){let e=this.internalProxyAnchor??document.createElement("a");return e.inert=!0,e}};g([h],O.prototype,"download",void 0);g([h],O.prototype,"href",void 0);g([h],O.prototype,"hreflang",void 0);g([h],O.prototype,"ping",void 0);g([h],O.prototype,"referrerpolicy",void 0);g([h],O.prototype,"rel",void 0);g([h],O.prototype,"target",void 0);g([h],O.prototype,"type",void 0);var En={filled:"filled",ghost:"ghost",outline:"outline",tint:"tint"},_n={brand:"brand",danger:"danger",important:"important",informative:"informative",severe:"severe",subtle:"subtle",success:"success",warning:"warning"};var Vn=`${k.prefix}-badge`;var jn=y.partial`
  ${De("inline-flex")} :host {
    position: relative;
    box-sizing: border-box;
    align-items: center;
    justify-content: center;
    font-family: ${Me};
    font-weight: ${Et};
    font-size: ${pe};
    line-height: ${ge};
    min-width: 20px;
    height: 20px;
    padding-inline: calc(${tt} + ${Re});
    border-radius: ${zt};
    border-color: ${Ie};
    background-color: ${Ft};
    color: ${Q};
    contain: content;
  }

  ::slotted(svg) {
    font-size: 12px;
  }

  :host(:not([appearance='ghost']))::after {
    position: absolute;
    content: '';
    top: 0;
    left: 0;
    bottom: 0;
    right: 0;
    border-style: solid;
    border-width: ${_t};
    border-color: inherit;
    border-radius: inherit;
  }
`,Gn=y.partial`
  :host([size='tiny']) {
    width: 6px;
    height: 6px;
    font-size: 4px;
    line-height: 4px;
    padding-inline: 0;
    min-width: unset;
  }
  :host([size='tiny']) ::slotted(svg) {
    font-size: 6px;
  }
  :host([size='extra-small']) {
    width: 10px;
    height: 10px;
    font-size: 6px;
    line-height: 6px;
    padding-inline: 0;
    min-width: unset;
  }
  :host([size='extra-small']) ::slotted(svg) {
    font-size: 10px;
  }
  :host([size='small']) {
    min-width: 16px;
    height: 16px;
    font-size: ${vn};
    line-height: ${Sn};
    padding-inline: calc(${Re} + ${Re});
  }
  :host([size='small']) ::slotted(svg) {
    font-size: 12px;
  }
  :host([size='large']) {
    min-width: 24px;
    height: 24px;
    font-size: ${pe};
    line-height: ${ge};
    padding-inline: calc(${tt} + ${Re});
  }
  :host([size='large']) ::slotted(svg) {
    font-size: 16px;
  }
  :host([size='extra-large']) {
    min-width: 32px;
    height: 32px;
    font-size: ${pe};
    line-height: ${ge};
    padding-inline: calc(${Vt} + ${Re});
  }
  :host([size='extra-large']) ::slotted(svg) {
    font-size: 20px;
  }
`,Wn=y.partial`
  :host([color='danger']) {
    background-color: ${Ct};
    color: ${Q};
  }

  :host([color='important']) {
    background-color: ${Le};
    color: ${be};
  }

  :host([color='informative']) {
    background-color: ${Wo};
    color: ${_};
  }

  :host([color='severe']) {
    background-color: ${It};
    color: ${Q};
  }

  :host([color='subtle']) {
    background-color: ${be};
    color: ${Le};
  }

  :host([color='success']) {
    background-color: ${Dt};
    color: ${Q};
  }

  :host([color='warning']) {
    background-color: ${hn};
    color: ${Eo};
  }
`,Xn=y.partial`
  :host([appearance='ghost']) {
    color: ${xr};
    background-color: initial;
  }

  :host([appearance='ghost'][color='danger']) {
    color: ${Pr};
  }

  :host([appearance='ghost'][color='important']) {
    color: ${Le};
  }

  :host([appearance='ghost'][color='informative']) {
    color: ${_};
  }

  :host([appearance='ghost'][color='severe']) {
    color: ${Nr};
  }

  :host([appearance='ghost'][color='subtle']) {
    color: ${Mo};
  }

  :host([appearance='ghost'][color='success']) {
    color: ${un};
  }

  :host([appearance='ghost'][color='warning']) {
    color: ${Mt};
  }
`,Un=y.partial`
  :host([appearance='outline']) {
    border-color: currentColor;
    color: ${xr};
    background-color: initial;
  }

  :host([appearance='outline'][color='danger']) {
    color: ${Pr};
  }

  :host([appearance='outline'][color='important']) {
    color: ${_};
    border-color: ${en};
  }

  :host([appearance='outline'][color='informative']) {
    color: ${_};
    border-color: ${Tt};
  }

  :host([appearance='outline'][color='severe']) {
    color: ${Nr};
  }

  :host([appearance='outline'][color='subtle']) {
    color: ${Ro};
  }

  :host([appearance='outline'][color='success']) {
    color: ${dn};
  }

  :host([appearance='outline'][color='warning']) {
    color: ${Mt};
  }
`,qn=y.partial`
  :host([appearance='tint']) {
    background-color: ${Zo};
    color: ${zo};
    border-color: ${on};
  }

  :host([appearance='tint'][color='danger']) {
    background-color: ${At};
    color: ${an};
    border-color: ${$t};
  }

  :host([appearance='tint'][color='important']) {
    background-color: ${_};
    color: ${be};
    border-color: ${Ie};
  }

  :host([appearance='tint'][color='informative']) {
    background-color: ${Go};
    color: ${_};
    border-color: ${Tt};
  }

  :host([appearance='tint'][color='severe']) {
    background-color: ${Lt};
    color: ${pn};
    border-color: ${Ot};
  }

  :host([appearance='tint'][color='subtle']) {
    background-color: ${be};
    color: ${_};
    border-color: ${Tt};
  }

  :host([appearance='tint'][color='success']) {
    background-color: ${Ht};
    color: ${cn};
    border-color: ${sn};
  }

  :host([appearance='tint'][color='warning']) {
    background-color: ${gn};
    color: ${Mt};
    border-color: ${fn};
  }
`;var Yn=y`
  :host([shape='square']) {
    border-radius: ${Oe};
  }

  :host([shape='rounded']) {
    border-radius: ${ue};
  }

  :host([shape='rounded']:is([size='tiny'], [size='extra-small'], [size='small'])) {
    border-radius: ${Rt};
  }

  ${qn}
  ${Un}
  ${Xn}
  ${Wn}
  ${Gn}
  ${jn}

  @media (forced-colors: active) {
    :host,
    :host([appearance='outline']),
    :host([appearance='tint']) {
      border-color: CanvasText;
    }
  }
`;function Zi(t={}){return A`
    ${$e(t)}
    <slot>${et(t.defaultContent)}</slot>
    ${Ce(t)}
  `}var Kn=Zi();var Jn={name:Vn,registry:k.registry,styles:Yn,template:Kn};var Z=class extends z{constructor(){super(...arguments),this.appearance=En.filled,this.color=_n.brand}};g([h],Z.prototype,"appearance",void 0);g([h],Z.prototype,"color",void 0);g([h],Z.prototype,"shape",void 0);g([h],Z.prototype,"size",void 0);He(Z,ce);var Fr=y`
  ${De("inline-flex")}

  :host {
    --icon-spacing: ${Vt};
    position: relative;
    contain: layout style;
    vertical-align: middle;
    align-items: center;
    box-sizing: border-box;
    justify-content: center;
    text-align: center;
    text-decoration-line: none;
    margin: 0;
    min-height: 32px;
    outline-style: none;
    background-color: ${be};
    color: ${Le};
    border: ${_t} solid ${wt};
    padding: 0 ${rt};
    min-width: 96px;
    border-radius: ${ue};
    font-size: ${bn};
    font-family: ${Me};
    font-weight: ${Et};
    line-height: ${yn};
    transition-duration: ${An};
    transition-property: background, border, color;
    transition-timing-function: ${Cn};
    cursor: pointer;
    user-select: none;
  }

  .content {
    display: inherit;
  }

  :host(:hover) {
    background-color: ${_o};
    color: ${Ho};
    border-color: ${tn};
  }

  :host(:hover:active) {
    background-color: ${Vo};
    border-color: ${rn};
    color: ${Do};
    outline-style: none;
  }

  :host(:focus-visible) {
    border-color: ${Ie};
    outline: ${Fn} solid ${Ie};
    box-shadow: ${Nn}, 0 0 0 2px ${kr};
  }

  @media screen and (prefers-reduced-motion: reduce) {
    :host {
      transition-duration: 0.01ms;
    }
  }

  ::slotted(svg) {
    font-size: 20px;
    height: 20px;
    width: 20px;
    fill: currentColor;
  }

  ::slotted([slot='start']) {
    margin-inline-end: var(--icon-spacing);
  }

  ::slotted([slot='end']),
  [slot='end'] {
    flex-shrink: 0;
    margin-inline-start: var(--icon-spacing);
  }

  :host([icon-only]) {
    min-width: 32px;
    max-width: 32px;
  }

  :host([size='small']) {
    --icon-spacing: ${tt};
    min-height: 24px;
    min-width: 64px;
    padding: 0 ${ze};
    border-radius: ${Rt};
    font-size: ${pe};
    line-height: ${ge};
    font-weight: ${xn};
  }

  :host([size='small'][icon-only]) {
    min-width: 24px;
    max-width: 24px;
  }

  :host([size='large']) {
    min-height: 40px;
    border-radius: ${mn};
    padding: 0 ${wn};
    font-size: ${Bn};
    line-height: ${kn};
  }

  :host([size='large'][icon-only]) {
    min-width: 40px;
    max-width: 40px;
  }

  :host([size='large']) ::slotted(svg) {
    font-size: 24px;
    height: 24px;
    width: 24px;
  }

  :host(:is([shape='circular'], [shape='circular']:focus-visible)) {
    border-radius: ${zt};
  }

  :host(:is([shape='square'], [shape='square']:focus-visible)) {
    border-radius: ${Oe};
  }

  :host([appearance='primary']) {
    background-color: ${Ft};
    color: ${Q};
    border-color: transparent;
  }

  :host([appearance='primary']:hover) {
    background-color: ${Ko};
  }

  :host([appearance='primary']:is(:hover, :hover:active):not(:focus-visible)) {
    border-color: transparent;
  }

  :host([appearance='primary']:is(:hover, :hover:active)) {
    color: ${Q};
  }

  :host([appearance='primary']:hover:active) {
    background-color: ${Jo};
  }

  :host([appearance='primary']:focus-visible) {
    border-color: ${Q};
    box-shadow: ${Pn}, 0 0 0 2px ${kr};
  }

  :host([appearance='outline']) {
    background-color: ${de};
  }

  :host([appearance='outline']:hover) {
    background-color: ${Sr};
  }

  :host([appearance='outline']:hover:active) {
    background-color: ${yr};
  }

  :host([appearance='subtle']) {
    background-color: ${Xo};
    color: ${vr};
    border-color: transparent;
  }

  :host([appearance='subtle']:hover) {
    background-color: ${Uo};
    color: ${Lo};
    border-color: transparent;
  }

  :host([appearance='subtle']:hover:active) {
    background-color: ${qo};
    color: ${Io};
    border-color: transparent;
  }

  :host([appearance='subtle']:hover) ::slotted(svg) {
    fill: ${br};
  }

  :host([appearance='subtle']:hover:active) ::slotted(svg) {
    fill: ${Br};
  }

  :host([appearance='transparent']) {
    background-color: ${de};
    color: ${vr};
  }

  :host([appearance='transparent']:hover) {
    background-color: ${Sr};
    color: ${br};
  }

  :host([appearance='transparent']:hover:active) {
    background-color: ${yr};
    color: ${Br};
  }

  :host(:is([appearance='transparent'], [appearance='transparent']:is(:hover, :active))) {
    border-color: transparent;
  }
`,Qn=y`
  ${Fr}

  :host(:is(:disabled, [disabled], [disabled-focusable], [appearance]:disabled, [appearance][disabled], [appearance][disabled-focusable])),
  :host(:is(:disabled, [disabled], [disabled-focusable], [appearance]:disabled, [appearance][disabled], [appearance][disabled-focusable]):hover),
  :host(:is(:disabled, [disabled], [disabled-focusable], [appearance]:disabled, [appearance][disabled], [appearance][disabled-focusable]):hover:active) {
    background-color: ${Yo};
    border-color: ${nn};
    color: ${Oo};
    cursor: not-allowed;
  }

  :host([appearance='primary']:is(:disabled, [disabled], [disabled-focusable])),
  :host([appearance='primary']:is(:disabled, [disabled], [disabled-focusable]):is(:hover, :hover:active)) {
    border-color: transparent;
  }

  :host([appearance='outline']:is(:disabled, [disabled], [disabled-focusable])),
  :host([appearance='outline']:is(:disabled, [disabled], [disabled-focusable]):is(:hover, :hover:active)) {
    background-color: ${de};
  }

  :host([appearance='subtle']:is(:disabled, [disabled], [disabled-focusable])),
  :host([appearance='subtle']:is(:disabled, [disabled], [disabled-focusable]):is(:hover, :hover:active)) {
    background-color: ${de};
    border-color: transparent;
  }

  :host([appearance='transparent']:is(:disabled, [disabled], [disabled-focusable])),
  :host([appearance='transparent']:is(:disabled, [disabled], [disabled-focusable]):is(:hover, :hover:active)) {
    border-color: transparent;
    background-color: ${de};
  }

  @media (forced-colors: active) {
    :host {
      background-color: ButtonFace;
      color: ButtonText;
    }

    :host(:is(:hover, :focus-visible)) {
      border-color: Highlight !important;
    }

    :host([appearance='primary']:not(:is(:hover, :focus-visible))) {
      background-color: Highlight;
      color: HighlightText;
      forced-color-adjust: none;
    }

    :host(
        :is(
            :disabled,
            [disabled],
            [disabled-focusable],
            [appearance]:disabled,
            [appearance][disabled],
            [appearance][disabled-focusable]
          )
      ) {
      background-color: ButtonFace;
      color: GrayText;
      border-color: ButtonText;
    }
  }
`;function el(t={}){return A`
    <template
      @click="${(e,r)=>e.clickHandler(r.event)}"
      @keypress="${(e,r)=>e.keypressHandler(r.event)}"
    >
      ${$e(t)}
      <span class="content" part="content">
        <slot ${mr("defaultSlottedContent")}></slot>
      </span>
      ${Ce(t)}
    </template>
  `}var Zn=el();var ea={name:Ln,registry:k.registry,styles:Qn,template:Zn};function ta(t){let e=t.ownerDocument;t?.isConnected&&t?.hasAttribute("autofocus")&&t?.checkVisibility?.({contentVisibilityAuto:!0,visibilityProperty:!0})&&[null,t,e.body,e.documentElement].includes(e.activeElement)&&M.enqueue(()=>{t.focus()})}var F=class extends z{disabledChanged(){this.setTabIndex()}disabledFocusableChanged(e,r){this.elementInternals&&(this.elementInternals.ariaDisabled=`${!!r}`)}get form(){return this.elementInternals.form}static{this.formAssociated=!0}get labels(){return Object.freeze(Array.from(this.elementInternals.labels))}typeChanged(e,r){r!==ot.submit&&(this.formSubmissionFallbackControl?.remove(),this.shadowRoot?.querySelector('slot[name="internal"]')?.remove())}clickHandler(e){if(e&&this.disabledFocusable){e.stopImmediatePropagation();return}return this.press(),!0}connectedCallback(){super.connectedCallback(),this.elementInternals.ariaDisabled=`${!!this.disabledFocusable}`,this.setTabIndex(),ta(this)}constructor(){super(),this.disabledFocusable=!1,this.elementInternals=this.attachInternals(),this.elementInternals.role="button"}createAndInsertFormSubmissionFallbackControl(){let e=this.formSubmissionFallbackControlSlot??document.createElement("slot");e.setAttribute("name","internal"),this.shadowRoot?.appendChild(e),this.formSubmissionFallbackControlSlot=e;let r=this.formSubmissionFallbackControl??document.createElement("button");r.style.display="none",r.setAttribute("type","submit"),r.setAttribute("slot","internal"),this.formNoValidate&&r.toggleAttribute("formnovalidate",!0),this.elementInternals.form?.id&&r.setAttribute("form",this.elementInternals.form.id),this.name&&r.setAttribute("name",this.name),this.value&&r.setAttribute("value",this.value),this.formAction&&r.setAttribute("formaction",this.formAction??""),this.formEnctype&&r.setAttribute("formenctype",this.formEnctype??""),this.formMethod&&r.setAttribute("formmethod",this.formMethod??""),this.formTarget&&r.setAttribute("formtarget",this.formTarget??""),this.append(r),this.formSubmissionFallbackControl=r}formDisabledCallback(e){this.disabled=e}keypressHandler(e){if(e&&this.disabledFocusable){e.stopImmediatePropagation();return}if(e.key==="Enter"||e.key===" "){this.click();return}return!0}press(){switch(this.type){case ot.reset:{this.resetForm();break}case ot.submit:{this.submitForm();break}}}resetForm(){this.elementInternals.form?.reset()}setTabIndex(){if(this.disabled){this.removeAttribute("tabindex");return}this.tabIndex=Number(this.getAttribute("tabindex")??0)<0?-1:0}submitForm(){if(!(!this.elementInternals.form||this.disabled||this.type!==ot.submit)){if(!this.name&&!this.formAction&&!this.formEnctype&&!this.formAttribute&&!this.formMethod&&!this.formNoValidate&&!this.formTarget){this.elementInternals.form.requestSubmit();return}try{this.elementInternals.setFormValue(this.value??""),this.elementInternals.form.requestSubmit(this)}catch{this.createAndInsertFormSubmissionFallbackControl(),this.elementInternals.setFormValue(null),this.elementInternals.form.requestSubmit(this.formSubmissionFallbackControl)}}}};g([je],F.prototype,"defaultSlottedContent",void 0);g([h({mode:"boolean"})],F.prototype,"disabled",void 0);g([h({attribute:"disabled-focusable",mode:"boolean"})],F.prototype,"disabledFocusable",void 0);g([h({attribute:"formaction"})],F.prototype,"formAction",void 0);g([h({attribute:"form"})],F.prototype,"formAttribute",void 0);g([h({attribute:"formenctype"})],F.prototype,"formEnctype",void 0);g([h({attribute:"formmethod"})],F.prototype,"formMethod",void 0);g([h({attribute:"formnovalidate",mode:"boolean"})],F.prototype,"formNoValidate",void 0);g([h({attribute:"formtarget"})],F.prototype,"formTarget",void 0);g([h],F.prototype,"name",void 0);g([h],F.prototype,"type",void 0);g([h],F.prototype,"value",void 0);var ee=class extends F{constructor(){super(...arguments),this.iconOnly=!1}};g([h],ee.prototype,"appearance",void 0);g([h],ee.prototype,"shape",void 0);g([h],ee.prototype,"size",void 0);g([h({attribute:"icon-only",mode:"boolean"})],ee.prototype,"iconOnly",void 0);He(ee,ce);var au=CSS.supports("anchor-name: --a"),iu="anchor"in HTMLElement.prototype,ra=CSS.supports("selector(:state(g))");function Gt(t,e,r){if(!(!e||!t)){if(!ra){t.shadowRoot.host.toggleAttribute(`state--${e}`,r);return}if(r??!t.states.has(e)){t.states.add(e);return}t.states.delete(e)}}var wr=new WeakMap;function tl(t,e){if(!t||!e)return!1;if(wr.has(t))return wr.get(t).has(e);let r=new Set(Object.values(t));return wr.set(t,r),r.has(e)}function Ee(t,e="",r="",o,n=""){Gt(t,`${n}${e}`,!1),(!o||tl(o,r))&&Gt(t,`${n}${r}`,!0)}var rl=0;function Tr(t="id-"){let e=`${t}${rl++}`;return document.getElementById(e)?Tr(t):e}var oa=y`
  ${Fr}

  ::slotted(a) {
    position: absolute;
    inset: 0;
  }

  @media (forced-colors: active) {
    :host {
      border-color: LinkText;
      color: LinkText;
    }
  }
`;function ol(t={}){return A`
    <template
      tabindex="0"
      @click="${(e,r)=>e.clickHandler(r.event)}"
      @keydown="${(e,r)=>e.keydownHandler(r.event)}"
    >
      ${$e(t)}
      <span class="content" part="content">
        <slot></slot>
      </span>
      ${Ce(t)}
    </template>
  `}var na=ol();var aa={name:zn,registry:k.registry,styles:oa,template:na};var te=class extends O{constructor(){super(...arguments),this.iconOnly=!1}appearanceChanged(e,r){Ee(this.elementInternals,e,r,In)}shapeChanged(e,r){Ee(this.elementInternals,e,r,On)}sizeChanged(e,r){Ee(this.elementInternals,e,r,Mn)}iconOnlyChanged(e,r){Gt(this.elementInternals,"icon",!!r)}};g([h],te.prototype,"appearance",void 0);g([h],te.prototype,"shape",void 0);g([h],te.prototype,"size",void 0);g([h({attribute:"icon-only",mode:"boolean"})],te.prototype,"iconOnly",void 0);He(te,ce);var ia=`${k.prefix}-message-bar`;var la=y`
  :host {
    display: grid;
    box-sizing: border-box;
    font-family: ${Me};
    font-size: ${pe};
    line-height: ${ge};
    width: 100%;
    background: ${jo};
    color: ${_};
    border: 1px solid ${wt};
    padding-inline: ${rt};
    border-radius: ${ue};
    min-height: 36px;
    align-items: center;
    grid-template: 'icon body actions dismiss' / auto 1fr auto auto;
    contain: layout style paint;
  }

  :host([shape='square']) {
    border-radius: 0;
  }

  :host([intent='success']) {
    background-color: ${Ht};
    border-color: ${ln};
  }

  :host([intent='warning']) {
    background-color: ${Lt};
    border-color: ${Ot};
  }

  :host([intent='error']) {
    background-color: ${At};
    border-color: ${$t};
  }

  :host([layout='multiline']) {
    grid-template-areas:
      'icon body dismiss'
      'actions actions actions';
    grid-template-columns: auto 1fr auto;
    grid-template-rows: auto auto 1fr;
    padding-block: ${jt};
    padding-inline: ${rt};
  }

  .content {
    grid-area: body;
    max-width: 520px;
    padding-block: ${jt};
    padding-inline: 0;
  }

  :host([layout='multiline']) .content {
    padding: 0;
  }

  ::slotted([slot='icon']) {
    display: flex;
    grid-area: icon;
    flex-direction: column;
    align-items: center;
    color: ${_};
    margin-inline-end: ${ze};
  }

  :host([layout='multiline']) ::slotted([slot='icon']) {
    align-items: start;
    height: 100%;
  }

  ::slotted([slot='dismiss']) {
    grid-area: dismiss;
  }

  .actions {
    grid-area: actions;
    display: flex;
    justify-self: end;
    margin-inline-end: ${ze};
    gap: ${ze};
  }

  :host([layout='multiline']) .actions {
    margin-block-start: ${jt};
    margin-inline-end: 0;
  }

  :host([layout='multiline']) ::slotted([slot='dismiss']) {
    align-items: start;
    height: 100%;
    padding-block-start: ${Tn};
  }

  ::slotted(*) {
    font-size: inherit;
  }
`;function nl(){return A`
    <slot name="icon"></slot>
    <div class="content">
      <slot></slot>
    </div>
    <div class="actions">
      <slot name="actions"></slot>
    </div>
    <slot name="dismiss"></slot>
  `}var sa=nl();var ca={name:ia,registry:k.registry,styles:la,template:sa};var Be=class extends z{constructor(){super(),this.elementInternals=this.attachInternals(),this.dismissMessageBar=()=>{this.$emit("dismiss",{})},this.elementInternals.role="status"}};g([h],Be.prototype,"shape",void 0);g([h],Be.prototype,"layout",void 0);g([h],Be.prototype,"intent",void 0);var da={success:"success",warning:"warning",error:"error"},ua=`${k.prefix}-progress-bar`;var pa=y`
  ${De("block")}

  :host {
    width: 100%;
    height: 2px;
    overflow-x: hidden;
    background-color: ${Nt};
    border-radius: ${ue};
    contain: content;

    @supports (width: attr(value type(<number>))) {
      --max: attr(max type(<number>), 100);
      --min: attr(min type(<number>), 0);
      --value: attr(value type(<number>), 0);
      --indicator-width: clamp(0%, calc((var(--value) - var(--min)) / (var(--max) - var(--min)) * 100%), 100%);
    }
  }

  :host([thickness='large']) {
    height: 4px;
  }

  :host([shape='square']) {
    border-radius: ${Oe};
  }

  .indicator {
    background-color: ${Qo};
    border-radius: inherit;
    height: 100%;
  }

  :host([value]) .indicator {
    transition: all 0.2s ease-in-out;

    @supports (width: attr(value type(<number>))) {
      width: var(--indicator-width);
    }
  }

  :host(:not([value])) .indicator {
    position: relative;
    width: 33%;
    background-image: linear-gradient(
      to right,
      ${Nt} 0%,
      ${de} 50%,
      ${Nt} 100%
    );
    animation-name: indeterminate;
    animation-duration: 3s;
    animation-timing-function: linear;
    animation-iteration-count: infinite;
  }

  :host([validation-state='error']) .indicator {
    background-color: ${Ct};
  }

  :host([validation-state='warning']) .indicator {
    background-color: ${It};
  }

  :host([validation-state='success']) .indicator {
    background-color: ${Dt};
  }

  @layer animations {
    /* Disable animations for reduced motion */
    @media (prefers-reduced-motion: no-preference) {
      :host([value]) {
        transition: none;
      }
      :host(:not([value])) .indicator {
        animation-duration: 0.01ms;
        animation-iteration-count: 1;
      }
    }
  }

  @keyframes indeterminate {
    0% {
      inset-inline-start: -33%;
    }
    100% {
      inset-inline-start: 100%;
    }
  }

  @media (forced-colors: active) {
    :host {
      background-color: CanvasText;
    }
    .indicator,
    :host(:is([validation-state='success'], [validation-state='warning'], [validation-state='error'])) .indicator {
      background-color: Highlight;
    }
  }
`;function al(){return A` <div class="indicator" part="indicator" ${Ae("indicator")}></div> `}var ga=al();var ha={name:ua,registry:k.registry,styles:pa,template:ga};var re=class extends z{indicatorChanged(){this.setIndicatorWidth()}validationStateChanged(e,r){Ee(this.elementInternals,e,r,da)}valueChanged(e,r){this.elementInternals&&(this.elementInternals.ariaValueNow=typeof r=="number"?`${r}`:null),this.setIndicatorWidth()}minChanged(e,r){this.elementInternals&&(this.elementInternals.ariaValueMin=typeof r=="number"?`${r}`:null),this.setIndicatorWidth()}maxChanged(e,r){this.elementInternals&&(this.elementInternals.ariaValueMax=typeof r=="number"?`${r}`:null),this.setIndicatorWidth()}constructor(){super(),this.elementInternals=this.attachInternals(),this.validationState=null,this.elementInternals.role="progressbar"}setIndicatorWidth(){CSS.supports("width: attr(value type(<number>))")||M.enqueue(()=>{if(typeof this.value!="number"){this.indicator?.style.removeProperty("width");return}let e=this.min??0,r=this.max??100,o=this.value??0,n=r-e,a=n===0?0:Math.fround((o-e)/n*100);this.indicator?.style.setProperty("width",`${a}%`)})}};g([je],re.prototype,"indicator",void 0);g([h({attribute:"validation-state"})],re.prototype,"validationState",void 0);g([h({converter:We})],re.prototype,"value",void 0);g([h({converter:We})],re.prototype,"min",void 0);g([h({converter:We})],re.prototype,"max",void 0);var _e=class extends re{};g([h],_e.prototype,"thickness",void 0);g([h],_e.prototype,"shape",void 0);var il="adoptedStyleSheets"in document,ll="CSSScopeRule"in window,Ar=new Map,Cr=new Map,at=new Map,$r=new Map,nt=new CSSStyleSheet;function Wt(t,e=document){if(!(!e||!sl(e))){if(!il||e instanceof HTMLElement&&!e.shadowRoot&&!ll){let r=e===document?document.documentElement:e;gl(t,r);return}[document,document.documentElement,document.body].includes(e)?cl(t):dl(t,e)}}function Hr(t){if(!Ar.has(t)){let e=[];for(let[r,o]of Object.entries(t))e.push(`--${r}:${o.toString()};`);Ar.set(t,e.join(""))}return Ar.get(t)}function sl(t){return[document,document.documentElement].includes(t)||t instanceof HTMLElement&&!!t.closest("body")}function cl(t){if(t===null){document.adoptedStyleSheets.includes(nt)&&nt.replaceSync("");return}nt.replaceSync(`
    html {
      ${Hr(t)}
    }
  `),document.adoptedStyleSheets.includes(nt)||document.adoptedStyleSheets.push(nt)}function dl(t,e){if(t===null){e.shadowRoot&&at.has(e)?at.get(e).replaceSync(""):(delete e.dataset.fluentTheme,fa(e));return}e.shadowRoot?ul(e).replaceSync(`
      :host {
        ${Hr(t)}
      }
    `):(e.dataset.fluentTheme=pl(t),fa(e))}function ul(t){if(!at.has(t)){let e=new CSSStyleSheet;at.set(t,e),t.shadowRoot?.adoptedStyleSheets.push(e)}return at.get(t)}function pl(t){if(!Cr.has(t)){let e=Tr("fluent-theme-"),r=new CSSStyleSheet;Cr.set(t,e),r.replaceSync(`
      @scope ([data-fluent-theme="${e}"]) {
        :scope {
          ${Hr(t)}
        }
      }
    `),document.adoptedStyleSheets.push(r)}return Cr.get(t)}function gl(t,e){let r;if(t===null){if(!$r.has(e))return;r=$r.get(e)}else $r.set(e,t),r=t;for(let[o,n]of Object.entries(r))t===null?e.style.removeProperty(`--${o}`):e.style.setProperty(`--${o}`,n.toString())}var{userAgent:hl}=navigator,fl=/\bAppleWebKit\/[\d+\.]+\b/.test(hl);function fa(t){if(!fl)return;let e="visibility",r="hidden",o=t.style.getPropertyValue(e);t.style.setProperty(e,r),M.process(),t.style.setProperty(e,o)}var d={2:"#050505",4:"#0a0a0a",6:"#0f0f0f",8:"#141414",10:"#1a1a1a",12:"#1f1f1f",14:"#242424",16:"#292929",18:"#2e2e2e",20:"#333333",22:"#383838",24:"#3d3d3d",26:"#424242",28:"#474747",30:"#4d4d4d",32:"#525252",34:"#575757",36:"#5c5c5c",38:"#616161",40:"#666666",42:"#6b6b6b",44:"#707070",46:"#757575",48:"#7a7a7a",50:"#808080",52:"#858585",54:"#8a8a8a",56:"#8f8f8f",58:"#949494",60:"#999999",62:"#9e9e9e",64:"#a3a3a3",66:"#a8a8a8",68:"#adadad",70:"#b3b3b3",72:"#b8b8b8",74:"#bdbdbd",76:"#c2c2c2",78:"#c7c7c7",80:"#cccccc",82:"#d1d1d1",84:"#d6d6d6",86:"#dbdbdb",88:"#e0e0e0",90:"#e6e6e6",92:"#ebebeb",94:"#f0f0f0",96:"#f5f5f5",98:"#fafafa",99:"#fcfcfc"},oe={5:"rgba(255, 255, 255, 0.05)",10:"rgba(255, 255, 255, 0.1)",20:"rgba(255, 255, 255, 0.2)",30:"rgba(255, 255, 255, 0.3)",40:"rgba(255, 255, 255, 0.4)",50:"rgba(255, 255, 255, 0.5)",60:"rgba(255, 255, 255, 0.6)",70:"rgba(255, 255, 255, 0.7)",80:"rgba(255, 255, 255, 0.8)",90:"rgba(255, 255, 255, 0.9)"},ne={5:"rgba(0, 0, 0, 0.05)",10:"rgba(0, 0, 0, 0.1)",20:"rgba(0, 0, 0, 0.2)",30:"rgba(0, 0, 0, 0.3)",40:"rgba(0, 0, 0, 0.4)",50:"rgba(0, 0, 0, 0.5)",60:"rgba(0, 0, 0, 0.6)",70:"rgba(0, 0, 0, 0.7)",80:"rgba(0, 0, 0, 0.8)",90:"rgba(0, 0, 0, 0.9)"};var v="#ffffff",ma="#000000";var va={shade50:"#130204",shade40:"#230308",shade30:"#420610",shade20:"#590815",shade10:"#690a19",primary:"#750b1c",tint10:"#861b2c",tint20:"#962f3f",tint30:"#ac4f5e",tint40:"#d69ca5",tint50:"#e9c7cd",tint60:"#f9f0f2"};var Dr={shade50:"#200205",shade40:"#3b0509",shade30:"#6e0811",shade20:"#960b18",shade10:"#b10e1c",primary:"#c50f1f",tint10:"#cc2635",tint20:"#d33f4c",tint30:"#dc626d",tint40:"#eeacb2",tint50:"#f6d1d5",tint60:"#fdf3f4"},ba={shade50:"#210809",shade40:"#3f1011",shade30:"#751d1f",shade20:"#9f282b",shade10:"#bc2f32",primary:"#d13438",tint10:"#d7494c",tint20:"#dc5e62",tint30:"#e37d80",tint40:"#f1bbbc",tint50:"#f8dadb",tint60:"#fdf6f6"},Ba={shade50:"#230900",shade40:"#411200",shade30:"#7a2101",shade20:"#a62d01",shade10:"#c43501",primary:"#da3b01",tint10:"#de501c",tint20:"#e36537",tint30:"#e9835e",tint40:"#f4bfab",tint50:"#f9dcd1",tint60:"#fdf6f3"};var xa={shade50:"#200d03",shade40:"#3d1805",shade30:"#712d09",shade20:"#9a3d0c",shade10:"#b6480e",primary:"#ca5010",tint10:"#d06228",tint20:"#d77440",tint30:"#df8e64",tint40:"#efc4ad",tint50:"#f7dfd2",tint60:"#fdf7f4"},Sa={shade50:"#271002",shade40:"#4a1e04",shade30:"#8a3707",shade20:"#bc4b09",shade10:"#de590b",primary:"#f7630c",tint10:"#f87528",tint20:"#f98845",tint30:"#faa06b",tint40:"#fdcfb4",tint50:"#fee5d7",tint60:"#fff9f5"},ya={shade50:"#291600",shade40:"#4d2a00",shade30:"#8f4e00",shade20:"#c26a00",shade10:"#e67e00",primary:"#ff8c00",tint10:"#ff9a1f",tint20:"#ffa83d",tint30:"#ffba66",tint40:"#ffddb3",tint50:"#ffedd6",tint60:"#fffaf5"},ka={shade50:"#251a00",shade40:"#463100",shade30:"#835b00",shade20:"#b27c00",shade10:"#d39300",primary:"#eaa300",tint10:"#edad1c",tint20:"#efb839",tint30:"#f2c661",tint40:"#f9e2ae",tint50:"#fcefd3",tint60:"#fefbf4"},Pa={shade50:"#282400",shade40:"#4c4400",shade30:"#817400",shade20:"#c0ad00",shade10:"#e4cc00",primary:"#fde300",tint10:"#fde61e",tint20:"#fdea3d",tint30:"#feee66",tint40:"#fef7b2",tint50:"#fffad6",tint60:"#fffef5"},Na={shade50:"#1f1900",shade40:"#3a2f00",shade30:"#6c5700",shade20:"#937700",shade10:"#ae8c00",primary:"#c19c00",tint10:"#c8a718",tint20:"#d0b232",tint30:"#dac157",tint40:"#ecdfa5",tint50:"#f5eece",tint60:"#fdfbf2"},Fa={shade50:"#181202",shade40:"#2e2103",shade30:"#553e06",shade20:"#745408",shade10:"#89640a",primary:"#986f0b",tint10:"#a47d1e",tint20:"#b18c34",tint30:"#c1a256",tint40:"#e0cea2",tint50:"#efe4cb",tint60:"#fbf8f2"},wa={shade50:"#170e07",shade40:"#2b1a0e",shade30:"#50301a",shade20:"#6c4123",shade10:"#804d29",primary:"#8e562e",tint10:"#9c663f",tint20:"#a97652",tint30:"#bb8f6f",tint40:"#ddc3b0",tint50:"#edded3",tint60:"#faf7f4"};var Ta={shade50:"#0c1501",shade40:"#162702",shade30:"#294903",shade20:"#376304",shade10:"#427505",primary:"#498205",tint10:"#599116",tint20:"#6ba02b",tint30:"#85b44c",tint40:"#bdd99b",tint50:"#dbebc7",tint60:"#f6faf0"},Aa={shade50:"#002111",shade40:"#003d20",shade30:"#00723b",shade20:"#009b51",shade10:"#00b85f",primary:"#00cc6a",tint10:"#19d279",tint20:"#34d889",tint30:"#5ae0a0",tint40:"#a8f0cd",tint50:"#cff7e4",tint60:"#f3fdf8"},Ca={shade50:"#031a02",shade40:"#063004",shade30:"#0b5a08",shade20:"#0e7a0b",shade10:"#11910d",primary:"#13a10e",tint10:"#27ac22",tint20:"#3db838",tint30:"#5ec75a",tint40:"#a7e3a5",tint50:"#cef0cd",tint60:"#f2fbf2"},Lr={shade50:"#031403",shade40:"#052505",shade30:"#094509",shade20:"#0c5e0c",shade10:"#0e700e",primary:"#107c10",tint10:"#218c21",tint20:"#359b35",tint30:"#54b054",tint40:"#9fd89f",tint50:"#c9eac9",tint60:"#f1faf1"},$a={shade50:"#021102",shade40:"#032003",shade30:"#063b06",shade20:"#085108",shade10:"#0a5f0a",primary:"#0b6a0b",tint10:"#1a7c1a",tint20:"#2d8e2d",tint30:"#4da64d",tint40:"#9ad29a",tint50:"#c6e7c6",tint60:"#f0f9f0"},Ha={shade50:"#001d1f",shade40:"#00373a",shade30:"#00666d",shade20:"#008b94",shade10:"#00a5af",primary:"#00b7c3",tint10:"#18bfca",tint20:"#32c8d1",tint30:"#58d3db",tint40:"#a6e9ed",tint50:"#cef3f5",tint60:"#f2fcfd"},Da={shade50:"#001516",shade40:"#012728",shade30:"#02494c",shade20:"#026467",shade10:"#037679",primary:"#038387",tint10:"#159195",tint20:"#2aa0a4",tint30:"#4cb4b7",tint40:"#9bd9db",tint50:"#c7ebec",tint60:"#f0fafa"};var La={shade50:"#000f12",shade40:"#001b22",shade30:"#00333f",shade20:"#004555",shade10:"#005265",primary:"#005b70",tint10:"#0f6c81",tint20:"#237d92",tint30:"#4496a9",tint40:"#94c8d4",tint50:"#c3e1e8",tint60:"#eff7f9"};var Ia={shade50:"#001322",shade40:"#002440",shade30:"#004377",shade20:"#005ba1",shade10:"#006cbf",primary:"#0078d4",tint10:"#1a86d9",tint20:"#3595de",tint30:"#5caae5",tint40:"#a9d3f2",tint50:"#d0e7f8",tint60:"#f3f9fd"},Oa={shade50:"#000c16",shade40:"#00172a",shade30:"#002c4e",shade20:"#003b6a",shade10:"#00467e",primary:"#004e8c",tint10:"#125e9a",tint20:"#286fa8",tint30:"#4a89ba",tint40:"#9abfdc",tint50:"#c7dced",tint60:"#f0f6fa"};var Ma={shade50:"#0d1126",shade40:"#182047",shade30:"#2c3c85",shade20:"#3c51b4",shade10:"#4760d5",primary:"#4f6bed",tint10:"#637cef",tint20:"#778df1",tint30:"#93a4f4",tint40:"#c8d1fa",tint50:"#e1e6fc",tint60:"#f7f9fe"},Ra={shade50:"#00061d",shade40:"#000c36",shade30:"#001665",shade20:"#001e89",shade10:"#0023a2",primary:"#0027b4",tint10:"#173bbd",tint20:"#3050c6",tint30:"#546fd2",tint40:"#a3b2e8",tint50:"#ccd5f3",tint60:"#f2f4fc"},za={shade50:"#120f25",shade40:"#221d46",shade30:"#3f3682",shade20:"#5649b0",shade10:"#6656d1",primary:"#7160e8",tint10:"#8172eb",tint20:"#9184ee",tint30:"#a79cf1",tint40:"#d2ccf8",tint50:"#e7e4fb",tint60:"#f9f8fe"},Ea={shade50:"#0f0717",shade40:"#1c0e2b",shade30:"#341a51",shade20:"#46236e",shade10:"#532982",primary:"#5c2e91",tint10:"#6b3f9e",tint20:"#7c52ab",tint30:"#9470bd",tint40:"#c6b1de",tint50:"#e0d3ed",tint60:"#f7f4fb"};var _a={shade50:"#160418",shade40:"#29072e",shade30:"#4c0d55",shade20:"#671174",shade10:"#7a1589",primary:"#881798",tint10:"#952aa4",tint20:"#a33fb1",tint30:"#b55fc1",tint40:"#d9a7e0",tint50:"#eaceef",tint60:"#faf2fb"},Va={shade50:"#1f091d",shade40:"#3a1136",shade30:"#6d2064",shade20:"#932b88",shade10:"#af33a1",primary:"#c239b3",tint10:"#c94cbc",tint20:"#d161c4",tint30:"#da7ed0",tint40:"#edbbe7",tint50:"#f5daf2",tint60:"#fdf5fc"},ja={shade50:"#1c0b1f",shade40:"#35153a",shade30:"#63276d",shade20:"#863593",shade10:"#9f3faf",primary:"#b146c2",tint10:"#ba58c9",tint20:"#c36bd1",tint30:"#cf87da",tint40:"#e6bfed",tint50:"#f2dcf5",tint60:"#fcf6fd"},Ga={shade50:"#24091b",shade40:"#441232",shade30:"#80215d",shade20:"#ad2d7e",shade10:"#cd3595",primary:"#e43ba6",tint10:"#e750b0",tint20:"#ea66ba",tint30:"#ef85c8",tint40:"#f7c0e3",tint50:"#fbddf0",tint60:"#fef6fb"};var Wa={shade50:"#1f0013",shade40:"#390024",shade30:"#6b0043",shade20:"#91005a",shade10:"#ac006b",primary:"#bf0077",tint10:"#c71885",tint20:"#ce3293",tint30:"#d957a8",tint40:"#eca5d1",tint50:"#f5cee6",tint60:"#fcf2f9"},Xa={shade50:"#13000c",shade40:"#240017",shade30:"#43002b",shade20:"#5a003b",shade10:"#6b0045",primary:"#77004d",tint10:"#87105d",tint20:"#98246f",tint30:"#ad4589",tint40:"#d696c0",tint50:"#e9c4dc",tint60:"#faf0f6"},Ua={shade50:"#141313",shade40:"#252323",shade30:"#444241",shade20:"#5d5958",shade10:"#6e6968",primary:"#7a7574",tint10:"#8a8584",tint20:"#9a9594",tint30:"#afabaa",tint40:"#d7d4d4",tint50:"#eae8e8",tint60:"#faf9f9"},qa={shade50:"#0f0e0e",shade40:"#1c1b1a",shade30:"#343231",shade20:"#474443",shade10:"#54514f",primary:"#5d5a58",tint10:"#706d6b",tint20:"#84817e",tint30:"#9e9b99",tint40:"#cecccb",tint50:"#e5e4e3",tint60:"#f8f8f8"};var Ya={shade50:"#111314",shade40:"#1f2426",shade30:"#3b4447",shade20:"#505c60",shade10:"#5f6d71",primary:"#69797e",tint10:"#79898d",tint20:"#89989d",tint30:"#a0adb2",tint40:"#cdd6d8",tint50:"#e4e9ea",tint60:"#f8f9fa"},Ka={shade50:"#090a0b",shade40:"#111315",shade30:"#202427",shade20:"#2b3135",shade10:"#333a3f",primary:"#394146",tint10:"#4d565c",tint20:"#626c72",tint30:"#808a90",tint40:"#bcc3c7",tint50:"#dbdfe1",tint60:"#f6f7f8"};var L={red:ba,green:Lr,darkOrange:Ba,yellow:Pa,berry:Va,lightGreen:Ca,marigold:ka},Xt={darkRed:va,cranberry:Dr,pumpkin:xa,peach:ya,gold:Na,brass:Fa,brown:wa,forest:Ta,seafoam:Aa,darkGreen:$a,lightTeal:Ha,teal:Da,steel:La,blue:Ia,royalBlue:Oa,cornflower:Ma,navy:Ra,lavender:za,purple:Ea,grape:_a,lilac:ja,pink:Ga,magenta:Wa,plum:Xa,beige:Ua,mink:qa,platinum:Ya,anchor:Ka},w={cranberry:Dr,green:Lr,orange:Sa};var Ja=["red","green","darkOrange","yellow","berry","lightGreen","marigold"],Qa=["darkRed","cranberry","pumpkin","peach","gold","brass","brown","forest","seafoam","darkGreen","lightTeal","teal","steel","blue","royalBlue","cornflower","navy","lavender","purple","grape","lilac","pink","magenta","plum","beige","mink","platinum","anchor"];var xe={success:"green",warning:"orange",danger:"cranberry"};var it=Ja.reduce((t,e)=>{let r=e.slice(0,1).toUpperCase()+e.slice(1),o={[`colorPalette${r}Background1`]:L[e].tint60,[`colorPalette${r}Background2`]:L[e].tint40,[`colorPalette${r}Background3`]:L[e].primary,[`colorPalette${r}Foreground1`]:L[e].shade10,[`colorPalette${r}Foreground2`]:L[e].shade30,[`colorPalette${r}Foreground3`]:L[e].primary,[`colorPalette${r}BorderActive`]:L[e].primary,[`colorPalette${r}Border1`]:L[e].tint40,[`colorPalette${r}Border2`]:L[e].primary};return Object.assign(t,o)},{});it.colorPaletteYellowForeground1=L.yellow.shade30;it.colorPaletteRedForegroundInverted=L.red.tint20;it.colorPaletteGreenForegroundInverted=L.green.tint20;it.colorPaletteYellowForegroundInverted=L.yellow.tint40;var ml=Qa.reduce((t,e)=>{let r=e.slice(0,1).toUpperCase()+e.slice(1),o={[`colorPalette${r}Background2`]:Xt[e].tint40,[`colorPalette${r}Foreground2`]:Xt[e].shade30,[`colorPalette${r}BorderActive`]:Xt[e].primary};return Object.assign(t,o)},{}),Za={...it,...ml},Se=Object.entries(xe).reduce((t,[e,r])=>{let o=e.slice(0,1).toUpperCase()+e.slice(1),n={[`colorStatus${o}Background1`]:w[r].tint60,[`colorStatus${o}Background2`]:w[r].tint40,[`colorStatus${o}Background3`]:w[r].primary,[`colorStatus${o}Foreground1`]:w[r].shade10,[`colorStatus${o}Foreground2`]:w[r].shade30,[`colorStatus${o}Foreground3`]:w[r].primary,[`colorStatus${o}ForegroundInverted`]:w[r].tint30,[`colorStatus${o}BorderActive`]:w[r].primary,[`colorStatus${o}Border1`]:w[r].tint40,[`colorStatus${o}Border2`]:w[r].primary};return Object.assign(t,n)},{});Se.colorStatusDangerBackground3Hover=w[xe.danger].shade10;Se.colorStatusDangerBackground3Pressed=w[xe.danger].shade20;Se.colorStatusWarningForeground1=w[xe.warning].shade20;Se.colorStatusWarningForeground3=w[xe.warning].shade20;Se.colorStatusWarningBorder2=w[xe.warning].shade20;var ei=t=>({colorNeutralForeground1:d[14],colorNeutralForeground1Hover:d[14],colorNeutralForeground1Pressed:d[14],colorNeutralForeground1Selected:d[14],colorNeutralForeground2:d[26],colorNeutralForeground2Hover:d[14],colorNeutralForeground2Pressed:d[14],colorNeutralForeground2Selected:d[14],colorNeutralForeground2BrandHover:t[80],colorNeutralForeground2BrandPressed:t[70],colorNeutralForeground2BrandSelected:t[80],colorNeutralForeground3:d[38],colorNeutralForeground3Hover:d[26],colorNeutralForeground3Pressed:d[26],colorNeutralForeground3Selected:d[26],colorNeutralForeground3BrandHover:t[80],colorNeutralForeground3BrandPressed:t[70],colorNeutralForeground3BrandSelected:t[80],colorNeutralForeground4:d[44],colorNeutralForeground5:d[38],colorNeutralForeground5Hover:d[14],colorNeutralForeground5Pressed:d[14],colorNeutralForeground5Selected:d[14],colorNeutralForegroundDisabled:d[74],colorNeutralForegroundInvertedDisabled:oe[40],colorBrandForegroundLink:t[70],colorBrandForegroundLinkHover:t[60],colorBrandForegroundLinkPressed:t[40],colorBrandForegroundLinkSelected:t[70],colorNeutralForeground2Link:d[26],colorNeutralForeground2LinkHover:d[14],colorNeutralForeground2LinkPressed:d[14],colorNeutralForeground2LinkSelected:d[14],colorCompoundBrandForeground1:t[80],colorCompoundBrandForeground1Hover:t[70],colorCompoundBrandForeground1Pressed:t[60],colorBrandForeground1:t[80],colorBrandForeground2:t[70],colorBrandForeground2Hover:t[60],colorBrandForeground2Pressed:t[30],colorNeutralForeground1Static:d[14],colorNeutralForegroundStaticInverted:v,colorNeutralForegroundInverted:v,colorNeutralForegroundInvertedHover:v,colorNeutralForegroundInvertedPressed:v,colorNeutralForegroundInvertedSelected:v,colorNeutralForegroundInverted2:v,colorNeutralForegroundOnBrand:v,colorNeutralForegroundInvertedLink:v,colorNeutralForegroundInvertedLinkHover:v,colorNeutralForegroundInvertedLinkPressed:v,colorNeutralForegroundInvertedLinkSelected:v,colorBrandForegroundInverted:t[100],colorBrandForegroundInvertedHover:t[110],colorBrandForegroundInvertedPressed:t[100],colorBrandForegroundOnLight:t[80],colorBrandForegroundOnLightHover:t[70],colorBrandForegroundOnLightPressed:t[50],colorBrandForegroundOnLightSelected:t[60],colorNeutralBackground1:v,colorNeutralBackground1Hover:d[96],colorNeutralBackground1Pressed:d[88],colorNeutralBackground1Selected:d[92],colorNeutralBackground2:d[98],colorNeutralBackground2Hover:d[94],colorNeutralBackground2Pressed:d[86],colorNeutralBackground2Selected:d[90],colorNeutralBackground3:d[96],colorNeutralBackground3Hover:d[92],colorNeutralBackground3Pressed:d[84],colorNeutralBackground3Selected:d[88],colorNeutralBackground4:d[94],colorNeutralBackground4Hover:d[98],colorNeutralBackground4Pressed:d[96],colorNeutralBackground4Selected:v,colorNeutralBackground5:d[92],colorNeutralBackground5Hover:d[96],colorNeutralBackground5Pressed:d[94],colorNeutralBackground5Selected:d[98],colorNeutralBackground6:d[90],colorNeutralBackground7:"#00000000",colorNeutralBackground7Hover:d[92],colorNeutralBackground7Pressed:d[84],colorNeutralBackground7Selected:"#00000000",colorNeutralBackground8:d[99],colorNeutralBackgroundInverted:d[16],colorNeutralBackgroundInvertedHover:d[24],colorNeutralBackgroundInvertedPressed:d[12],colorNeutralBackgroundInvertedSelected:d[22],colorNeutralBackgroundStatic:d[20],colorNeutralBackgroundAlpha:oe[50],colorNeutralBackgroundAlpha2:oe[80],colorSubtleBackground:"transparent",colorSubtleBackgroundHover:d[96],colorSubtleBackgroundPressed:d[88],colorSubtleBackgroundSelected:d[92],colorSubtleBackgroundLightAlphaHover:oe[70],colorSubtleBackgroundLightAlphaPressed:oe[50],colorSubtleBackgroundLightAlphaSelected:"transparent",colorSubtleBackgroundInverted:"transparent",colorSubtleBackgroundInvertedHover:ne[10],colorSubtleBackgroundInvertedPressed:ne[30],colorSubtleBackgroundInvertedSelected:ne[20],colorTransparentBackground:"transparent",colorTransparentBackgroundHover:"transparent",colorTransparentBackgroundPressed:"transparent",colorTransparentBackgroundSelected:"transparent",colorNeutralBackgroundDisabled:d[94],colorNeutralBackgroundDisabled2:v,colorNeutralBackgroundInvertedDisabled:oe[10],colorNeutralStencil1:d[90],colorNeutralStencil2:d[98],colorNeutralStencil1Alpha:ne[10],colorNeutralStencil2Alpha:ne[5],colorBackgroundOverlay:ne[40],colorScrollbarOverlay:ne[50],colorBrandBackground:t[80],colorBrandBackgroundHover:t[70],colorBrandBackgroundPressed:t[40],colorBrandBackgroundSelected:t[60],colorCompoundBrandBackground:t[80],colorCompoundBrandBackgroundHover:t[70],colorCompoundBrandBackgroundPressed:t[60],colorBrandBackgroundStatic:t[80],colorBrandBackground2:t[160],colorBrandBackground2Hover:t[150],colorBrandBackground2Pressed:t[130],colorBrandBackground3Static:t[60],colorBrandBackground4Static:t[40],colorBrandBackgroundInverted:v,colorBrandBackgroundInvertedHover:t[160],colorBrandBackgroundInvertedPressed:t[140],colorBrandBackgroundInvertedSelected:t[150],colorNeutralCardBackground:d[98],colorNeutralCardBackgroundHover:v,colorNeutralCardBackgroundPressed:d[96],colorNeutralCardBackgroundSelected:d[92],colorNeutralCardBackgroundDisabled:d[94],colorNeutralStrokeAccessible:d[38],colorNeutralStrokeAccessibleHover:d[34],colorNeutralStrokeAccessiblePressed:d[30],colorNeutralStrokeAccessibleSelected:t[80],colorNeutralStroke1:d[82],colorNeutralStroke1Hover:d[78],colorNeutralStroke1Pressed:d[70],colorNeutralStroke1Selected:d[74],colorNeutralStroke2:d[88],colorNeutralStroke3:d[94],colorNeutralStroke4:d[92],colorNeutralStroke4Hover:d[88],colorNeutralStroke4Pressed:d[84],colorNeutralStroke4Selected:d[92],colorNeutralStrokeSubtle:d[88],colorNeutralStrokeOnBrand:v,colorNeutralStrokeOnBrand2:v,colorNeutralStrokeOnBrand2Hover:v,colorNeutralStrokeOnBrand2Pressed:v,colorNeutralStrokeOnBrand2Selected:v,colorBrandStroke1:t[80],colorBrandStroke2:t[140],colorBrandStroke2Hover:t[120],colorBrandStroke2Pressed:t[80],colorBrandStroke2Contrast:t[140],colorCompoundBrandStroke:t[80],colorCompoundBrandStrokeHover:t[70],colorCompoundBrandStrokePressed:t[60],colorNeutralStrokeDisabled:d[88],colorNeutralStrokeDisabled2:d[92],colorNeutralStrokeInvertedDisabled:oe[40],colorTransparentStroke:"transparent",colorTransparentStrokeInteractive:"transparent",colorTransparentStrokeDisabled:"transparent",colorNeutralStrokeAlpha:ne[5],colorNeutralStrokeAlpha2:oe[20],colorStrokeFocus1:v,colorStrokeFocus2:ma,colorNeutralShadowAmbient:"rgba(0,0,0,0.12)",colorNeutralShadowKey:"rgba(0,0,0,0.14)",colorNeutralShadowAmbientLighter:"rgba(0,0,0,0.06)",colorNeutralShadowKeyLighter:"rgba(0,0,0,0.07)",colorNeutralShadowAmbientDarker:"rgba(0,0,0,0.20)",colorNeutralShadowKeyDarker:"rgba(0,0,0,0.24)",colorBrandShadowAmbient:"rgba(0,0,0,0.30)",colorBrandShadowKey:"rgba(0,0,0,0.25)"});var Ir={borderRadiusNone:"0",borderRadiusSmall:"2px",borderRadiusMedium:"4px",borderRadiusLarge:"6px",borderRadiusXLarge:"8px",borderRadius2XLarge:"12px",borderRadius3XLarge:"16px",borderRadius4XLarge:"24px",borderRadius5XLarge:"32px",borderRadius6XLarge:"40px",borderRadiusCircular:"10000px"};var ti={curveAccelerateMax:"cubic-bezier(0.9,0.1,1,0.2)",curveAccelerateMid:"cubic-bezier(1,0,1,1)",curveAccelerateMin:"cubic-bezier(0.8,0,0.78,1)",curveDecelerateMax:"cubic-bezier(0.1,0.9,0.2,1)",curveDecelerateMid:"cubic-bezier(0,0,0,1)",curveDecelerateMin:"cubic-bezier(0.33,0,0.1,1)",curveEasyEaseMax:"cubic-bezier(0.8,0,0.2,1)",curveEasyEase:"cubic-bezier(0.33,0,0.67,1)",curveLinear:"cubic-bezier(0,0,1,1)"};var ri={durationUltraFast:"50ms",durationFaster:"100ms",durationFast:"150ms",durationNormal:"200ms",durationGentle:"250ms",durationSlow:"300ms",durationSlower:"400ms",durationUltraSlow:"500ms"};var Or={fontSizeBase100:"10px",fontSizeBase200:"12px",fontSizeBase300:"14px",fontSizeBase400:"16px",fontSizeBase500:"20px",fontSizeBase600:"24px",fontSizeHero700:"28px",fontSizeHero800:"32px",fontSizeHero900:"40px",fontSizeHero1000:"68px"},Mr={lineHeightBase100:"14px",lineHeightBase200:"16px",lineHeightBase300:"20px",lineHeightBase400:"22px",lineHeightBase500:"28px",lineHeightBase600:"32px",lineHeightHero700:"36px",lineHeightHero800:"40px",lineHeightHero900:"52px",lineHeightHero1000:"92px"},Rr={fontWeightRegular:400,fontWeightMedium:500,fontWeightSemibold:600,fontWeightBold:700},zr={fontFamilyBase:"'Segoe UI', 'Segoe UI Web (West European)', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif",fontFamilyMonospace:"Consolas, 'Courier New', Courier, monospace",fontFamilyNumeric:"Bahnschrift, 'Segoe UI', 'Segoe UI Web (West European)', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif"};var B={none:"0",xxs:"2px",xs:"4px",sNudge:"6px",s:"8px",mNudge:"10px",m:"12px",l:"16px",xl:"20px",xxl:"24px",xxxl:"32px"},oi={spacingHorizontalNone:B.none,spacingHorizontalXXS:B.xxs,spacingHorizontalXS:B.xs,spacingHorizontalSNudge:B.sNudge,spacingHorizontalS:B.s,spacingHorizontalMNudge:B.mNudge,spacingHorizontalM:B.m,spacingHorizontalL:B.l,spacingHorizontalXL:B.xl,spacingHorizontalXXL:B.xxl,spacingHorizontalXXXL:B.xxxl},ni={spacingVerticalNone:B.none,spacingVerticalXXS:B.xxs,spacingVerticalXS:B.xs,spacingVerticalSNudge:B.sNudge,spacingVerticalS:B.s,spacingVerticalMNudge:B.mNudge,spacingVerticalM:B.m,spacingVerticalL:B.l,spacingVerticalXL:B.xl,spacingVerticalXXL:B.xxl,spacingVerticalXXXL:B.xxxl};var Er={strokeWidthThin:"1px",strokeWidthThick:"2px",strokeWidthThicker:"3px",strokeWidthThickest:"4px"};function _r(t,e,r=""){return{[`shadow2${r}`]:`0 0 2px ${t}, 0 1px 2px ${e}`,[`shadow4${r}`]:`0 0 2px ${t}, 0 2px 4px ${e}`,[`shadow8${r}`]:`0 0 2px ${t}, 0 4px 8px ${e}`,[`shadow16${r}`]:`0 0 2px ${t}, 0 8px 16px ${e}`,[`shadow28${r}`]:`0 0 8px ${t}, 0 14px 28px ${e}`,[`shadow64${r}`]:`0 0 8px ${t}, 0 32px 64px ${e}`}}var ai=t=>{let e=ei(t);return{...Ir,...Or,...Mr,...zr,...Rr,...Er,...oi,...ni,...ri,...ti,...e,...Za,...Se,..._r(e.colorNeutralShadowAmbient,e.colorNeutralShadowKey),..._r(e.colorBrandShadowAmbient,e.colorBrandShadowKey,"Brand")}};var ii={10:"#061724",20:"#082338",30:"#0a2e4a",40:"#0c3b5e",50:"#0e4775",60:"#0f548c",70:"#115ea3",80:"#0f6cbd",90:"#2886de",100:"#479ef5",110:"#62abf5",120:"#77b7f7",130:"#96c6fa",140:"#b4d6fa",150:"#cfe4fa",160:"#ebf3fc"};var lt=ai(ii);te.define(aa);Z.define(Jn);ee.define(ea);Be.define(ca);_e.define(ha);Wt(lt);
