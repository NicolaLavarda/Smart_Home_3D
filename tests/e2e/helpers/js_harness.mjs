import fs from 'node:fs';
import path from 'node:path';
import { createServer } from 'vite';

// ============================================================================
// Minimal DOM & Browser Environment Shim
// ============================================================================

function parseAttributes(rawAttrs) {
  const attrs = {};
  const re = /([a-zA-Z_:][a-zA-Z0-9_.:-]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  let m;
  while ((m = re.exec(rawAttrs)) !== null) {
    const key = m[1].toLowerCase();
    const val = m[2] ?? m[3] ?? m[4] ?? '';
    attrs[key] = val;
  }
  return attrs;
}

const VOID_TAGS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
  'link', 'meta', 'param', 'source', 'track', 'wbr',
  'path', 'circle', 'rect', 'line', 'polygon', 'polyline', 'ellipse',
]);

class TextNode {
  constructor(text, ownerDocument) {
    this.nodeType = 3;
    this.nodeName = '#text';
    this.textContent = String(text ?? '');
    this.parentNode = null;
    this.ownerDocument = ownerDocument;
  }
  remove() {
    if (this.parentNode) {
      this.parentNode.removeChild(this);
    }
  }
}

class ClassList {
  constructor(el) {
    this.el = el;
  }
  _getTokens() {
    const raw = this.el._attrs.class || '';
    return raw.trim() ? raw.trim().split(/\s+/) : [];
  }
  _setTokens(tokens) {
    this.el._attrs.class = tokens.join(' ');
  }
  add(...names) {
    const set = new Set(this._getTokens());
    for (const n of names) {
      if (n) set.add(n);
    }
    this._setTokens(Array.from(set));
  }
  remove(...names) {
    const rm = new Set(names);
    this._setTokens(this._getTokens().filter((t) => !rm.has(t)));
  }
  toggle(name, force) {
    const has = this.contains(name);
    const shouldAdd = force !== undefined ? Boolean(force) : !has;
    if (shouldAdd) this.add(name);
    else this.remove(name);
    return shouldAdd;
  }
  contains(name) {
    return this._getTokens().includes(name);
  }
  toString() {
    return this.el._attrs.class || '';
  }
}

function matchSimpleSelector(el, simple) {
  if (!el || el.nodeType !== 1) return false;
  let rest = simple.trim();
  if (!rest) return false;
  if (rest === '*') return true;

  // Handle :not(...)
  const notMatches = [];
  rest = rest.replace(/:not\(([^)]+)\)/g, (_, inner) => {
    notMatches.push(inner.trim());
    return '';
  });

  // Extract attribute selectors [...]
  const attrChecks = [];
  rest = rest.replace(/\[([^\]]+)\]/g, (_, expr) => {
    attrChecks.push(expr.trim());
    return '';
  });

  // Extract tag name (leading)
  const tagMatch = rest.match(/^[a-zA-Z0-9_-]+/);
  if (tagMatch) {
    if (el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    rest = rest.slice(tagMatch[0].length);
  }

  // Extract #id and .class tokens
  const idMatches = rest.match(/#[a-zA-Z0-9_-]+/g) || [];
  for (const idTok of idMatches) {
    if (el.id !== idTok.slice(1)) return false;
  }
  const classMatches = rest.match(/\.[a-zA-Z0-9_-]+/g) || [];
  for (const clsTok of classMatches) {
    if (!el.classList.contains(clsTok.slice(1))) return false;
  }

  for (const expr of attrChecks) {
    const m = expr.match(/^([a-zA-Z0-9_:-]+)\s*([*^$~|]?=)\s*(?:"([^"]*)"|'([^']*)'|([^\s]+))(\s+i)?$/i);
    if (!m) {
      if (!el.hasAttribute(expr.toLowerCase())) return false;
    } else {
      const attrName = m[1].toLowerCase();
      const op = m[2];
      const expected = m[3] ?? m[4] ?? m[5] ?? '';
      const ci = Boolean(m[6]);
      if (!el.hasAttribute(attrName)) return false;
      let actual = String(el.getAttribute(attrName) ?? '');
      let exp = expected;
      if (ci) {
        actual = actual.toLowerCase();
        exp = exp.toLowerCase();
      }
      if (op === '=' && actual !== exp) return false;
      if (op === '*=' && !actual.includes(exp)) return false;
      if (op === '^=' && !actual.startsWith(exp)) return false;
      if (op === '$=' && !actual.endsWith(exp)) return false;
      if (op === '~=' && !actual.split(/\s+/).includes(exp)) return false;
    }
  }

  for (const neg of notMatches) {
    if (matchSimpleSelector(el, neg)) return false;
  }
  return true;
}

function matchSingleSelectorChain(el, selectorChain) {
  const parts = selectorChain.trim().replace(/\s*>\s*/g, ' > ').split(/\s+/);
  if (parts.length === 0) return false;
  const last = parts[parts.length - 1];
  if (!matchSimpleSelector(el, last)) return false;

  let cur = el;
  let i = parts.length - 2;
  while (i >= 0) {
    if (parts[i] === '>') {
      i -= 1;
      cur = cur.parentNode;
      if (!cur || cur.nodeType !== 1 || !matchSimpleSelector(cur, parts[i])) return false;
      i -= 1;
    } else {
      let ancestor = cur.parentNode;
      let found = false;
      while (ancestor && ancestor.nodeType === 1) {
        if (matchSimpleSelector(ancestor, parts[i])) {
          cur = ancestor;
          found = true;
          break;
        }
        ancestor = ancestor.parentNode;
      }
      if (!found) return false;
      i -= 1;
    }
  }
  return true;
}

function matchesSelector(el, selector) {
  if (!selector || typeof selector !== 'string') return false;
  return selector.split(',').some((s) => matchSingleSelectorChain(el, s));
}

function buildHtmlNodes(html, ownerDocument, namespaceURI = null) {
  const root = { childNodes: [] };
  const stack = [{ node: root, ns: namespaceURI }];
  const str = String(html ?? '');
  let pos = 0;

  while (pos < str.length) {
    const lt = str.indexOf('<', pos);
    if (lt === -1) {
      const txt = str.slice(pos);
      if (txt) {
        stack[stack.length - 1].node.childNodes.push(new TextNode(txt, ownerDocument));
      }
      break;
    }
    if (lt > pos) {
      const txt = str.slice(pos, lt);
      if (txt) {
        stack[stack.length - 1].node.childNodes.push(new TextNode(txt, ownerDocument));
      }
    }

    // Comment
    if (str.startsWith('<!--', lt)) {
      const endComment = str.indexOf('-->', lt + 4);
      pos = endComment === -1 ? str.length : endComment + 3;
      continue;
    }

    const gt = str.indexOf('>', lt + 1);
    if (gt === -1) break;
    const rawTag = str.slice(lt + 1, gt).trim();
    pos = gt + 1;

    if (rawTag.startsWith('/')) {
      const closeTag = rawTag.slice(1).trim().toLowerCase();
      for (let idx = stack.length - 1; idx >= 1; idx--) {
        if (stack[idx].node.tagName.toLowerCase() === closeTag) {
          stack.length = idx;
          break;
        }
      }
      continue;
    }

    const selfClosing = rawTag.endsWith('/');
    const tagContent = selfClosing ? rawTag.slice(0, -1).trim() : rawTag;
    const spaceIdx = tagContent.search(/\s/);
    const tagName = (spaceIdx === -1 ? tagContent : tagContent.slice(0, spaceIdx)).toLowerCase();
    const rawAttrs = spaceIdx === -1 ? '' : tagContent.slice(spaceIdx + 1);

    const parentEntry = stack[stack.length - 1];
    const childNs = tagName === 'svg' ? 'http://www.w3.org/2000/svg' : parentEntry.ns;
    const el = childNs
      ? ownerDocument.createElementNS(childNs, tagName)
      : ownerDocument.createElement(tagName);
    const parsedAttrs = parseAttributes(rawAttrs);
    for (const [k, v] of Object.entries(parsedAttrs)) {
      el.setAttribute(k, v);
    }

    if (parentEntry.node === root) {
      el.parentNode = null;
      root.childNodes.push(el);
    } else {
      parentEntry.node.appendChild(el);
    }

    if (!selfClosing && !VOID_TAGS.has(tagName)) {
      stack.push({ node: el, ns: childNs });
    }
  }

  for (const child of root.childNodes) {
    if (child.nodeType === 1) child.parentNode = null;
  }
  return root.childNodes;
}

class DomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = Boolean(init.bubbles);
    this.cancelable = Boolean(init.cancelable);
    this.defaultPrevented = false;
    this.cancelBubble = false;
    this.target = init.target || null;
    this.currentTarget = null;
    this.pointerType = init.pointerType || 'mouse';
    this.button = init.button ?? 0;
    this.pointerId = init.pointerId ?? 1;
    this.clientX = init.clientX ?? 0;
    this.clientY = init.clientY ?? 0;
    this.key = init.key ?? '';
  }
  preventDefault() {
    this.defaultPrevented = true;
  }
  stopPropagation() {
    this.cancelBubble = true;
  }
}

function createMock2DContext() {
  const noop = () => {};
  const grad = { addColorStop: noop };
  return {
    fillStyle: '#000',
    strokeStyle: '#000',
    lineWidth: 1,
    font: '12px sans-serif',
    textAlign: 'left',
    fillRect: noop,
    strokeRect: noop,
    clearRect: noop,
    beginPath: noop,
    closePath: noop,
    moveTo: noop,
    lineTo: noop,
    arc: noop,
    stroke: noop,
    fill: noop,
    fillText: noop,
    drawImage: noop,
    save: noop,
    restore: noop,
    createLinearGradient: () => grad,
    createRadialGradient: () => grad,
  };
}

function createWebGL2Proxy() {
  const CONSTANTS = {
    VENDOR: 0x1F00,
    RENDERER: 0x1F01,
    VERSION: 0x1F02,
    SHADING_LANGUAGE_VERSION: 0x8B8C,
    EXTENSIONS: 0x1F03,
    MAX_VERTEX_ATTRIBS: 0x8B4C,
    MAX_TEXTURE_IMAGE_UNITS: 0x8872,
    MAX_VERTEX_TEXTURE_IMAGE_UNITS: 0x8B4C,
    MAX_COMBINED_TEXTURE_IMAGE_UNITS: 0x8B4D,
    MAX_VARYING_VECTORS: 0x8DFB,
    MAX_VERTEX_UNIFORM_VECTORS: 0x8DF9,
    MAX_FRAGMENT_UNIFORM_VECTORS: 0x8DFD,
    MAX_TEXTURE_SIZE: 0x0D33,
    MAX_CUBE_MAP_TEXTURE_SIZE: 0x851C,
    MAX_RENDERBUFFER_SIZE: 0x84E8,
    MAX_SAMPLES: 0x8D57,
    MAX_VIEWPORT_DIMS: 0x0D3A,
    FRAMEBUFFER_COMPLETE: 0x8CD5,
    COLOR_BUFFER_BIT: 0x4000,
    DEPTH_BUFFER_BIT: 0x0100,
    STENCIL_BUFFER_BIT: 0x0400,
    TRIANGLES: 0x0004,
    UNSIGNED_BYTE: 0x1401,
    FLOAT: 0x1406,
    RGBA: 0x1908,
    TEXTURE_2D: 0x0DE1,
    SCISSOR_TEST: 0x0C11,
    DEPTH_TEST: 0x0B71,
    BLEND: 0x0BE2,
    CULL_FACE: 0x0B44,
    ARRAY_BUFFER: 0x8892,
    ELEMENT_ARRAY_BUFFER: 0x8893,
    STATIC_DRAW: 0x88E4,
    VERTEX_SHADER: 0x8B31,
    FRAGMENT_SHADER: 0x8B30,
    COMPILE_STATUS: 0x8B81,
    LINK_STATUS: 0x8B82,
    ACTIVE_UNIFORMS: 0x8B86,
    ACTIVE_ATTRIBUTES: 0x8B89,
  };
  const params = new Map([
    [CONSTANTS.VENDOR, 'WebKit'],
    [CONSTANTS.RENDERER, 'WebKit WebGL'],
    [CONSTANTS.VERSION, 'WebGL 2.0 (OpenGL ES 3.0)'],
    [CONSTANTS.SHADING_LANGUAGE_VERSION, 'WebGL GLSL ES 3.00'],
    [CONSTANTS.MAX_VERTEX_ATTRIBS, 16],
    [CONSTANTS.MAX_TEXTURE_IMAGE_UNITS, 16],
    [CONSTANTS.MAX_COMBINED_TEXTURE_IMAGE_UNITS, 32],
    [CONSTANTS.MAX_VARYING_VECTORS, 15],
    [CONSTANTS.MAX_VERTEX_UNIFORM_VECTORS, 256],
    [CONSTANTS.MAX_FRAGMENT_UNIFORM_VECTORS, 256],
    [CONSTANTS.MAX_TEXTURE_SIZE, 4096],
    [CONSTANTS.MAX_CUBE_MAP_TEXTURE_SIZE, 4096],
    [CONSTANTS.MAX_RENDERBUFFER_SIZE, 4096],
    [CONSTANTS.MAX_SAMPLES, 4],
    [CONSTANTS.MAX_VIEWPORT_DIMS, new Int32Array([4096, 4096])],
  ]);
  const noop = () => {};
  return new Proxy({}, {
    get(_target, prop) {
      if (typeof prop === 'string' && Object.prototype.hasOwnProperty.call(CONSTANTS, prop)) {
        return CONSTANTS[prop];
      }
      if (typeof prop === 'string' && /^[A-Z0-9_]+$/.test(prop)) {
        return 0x1000;
      }
      if (prop === 'getParameter') return (p) => params.get(p) ?? 16;
      if (prop === 'getExtension') return () => ({});
      if (prop === 'getSupportedExtensions') return () => [];
      if (prop === 'getContextAttributes') return () => ({ alpha: false, antialias: true, depth: true, stencil: true });
      if (prop === 'getShaderPrecisionFormat') return () => ({ rangeMin: 127, rangeMax: 127, precision: 23 });
      if (prop === 'createShader' || prop === 'createProgram' || prop === 'createBuffer' ||
          prop === 'createTexture' || prop === 'createFramebuffer' || prop === 'createRenderbuffer' ||
          prop === 'createVertexArray' || prop === 'getUniformLocation') return () => ({});
      if (prop === 'getAttribLocation') return () => 0;
      if (prop === 'getShaderParameter' || prop === 'getProgramParameter') return () => true;
      if (prop === 'getProgramInfoLog' || prop === 'getShaderInfoLog') return () => '';
      if (prop === 'checkFramebufferStatus') return () => CONSTANTS.FRAMEBUFFER_COMPLETE;
      if (prop === 'isContextLost') return () => false;
      if (prop === 'canvas') return null;
      return noop;
    },
  });
}

class DomElement {
  constructor(tagName, ownerDocument, namespaceURI = null) {
    this.nodeType = 1;
    this.tagName = String(tagName).toUpperCase();
    this.nodeName = this.tagName;
    this.namespaceURI = namespaceURI;
    this.ownerDocument = ownerDocument;
    this.parentNode = null;
    this.childNodes = [];
    this._attrs = {};
    this._listeners = new Map();
    this._styleObj = {};
    this.classList = new ClassList(this);
    this.src = '';
    this.srcObject = null;
    this.muted = false;
    this.autoplay = false;
    this.playsInline = false;
    this.crossOrigin = null;
    this.disableRemotePlayback = false;
    this.currentTime = 0;
    this.buffered = { length: 0, end: () => 0 };
    this.width = 300;
    this.height = 150;
    this.value = '';
    this.min = '';
    this.max = '';
    this.step = '';
    this.type = '';

    this.style = new Proxy(this._styleObj, {
      set: (target, prop, val) => {
        if (prop === 'cssText') {
          for (const k of Object.keys(target)) delete target[k];
          for (const rule of String(val || '').split(';')) {
            const idx = rule.indexOf(':');
            if (idx > 0) {
              const k = rule.slice(0, idx).trim();
              const v = rule.slice(idx + 1).trim();
              target[k] = v;
            }
          }
          return true;
        }
        target[prop] = val;
        return true;
      },
      get: (target, prop) => {
        if (prop === 'setProperty') return (k, v) => { target[k] = v; };
        if (prop === 'getPropertyValue') return (k) => target[k] || '';
        return target[prop] ?? '';
      },
    });

    this.dataset = new Proxy({}, {
      get: (_t, prop) => {
        const attrKey = 'data-' + String(prop).replace(/[A-Z]/g, (m) => '-' + m.toLowerCase());
        return this._attrs[attrKey];
      },
      set: (_t, prop, val) => {
        const attrKey = 'data-' + String(prop).replace(/[A-Z]/g, (m) => '-' + m.toLowerCase());
        this._attrs[attrKey] = String(val);
        return true;
      },
    });
  }

  get parentElement() {
    return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null;
  }

  get children() {
    return this.childNodes.filter((c) => c.nodeType === 1);
  }

  get firstChild() {
    return this.childNodes[0] || null;
  }

  get lastChild() {
    return this.childNodes[this.childNodes.length - 1] || null;
  }

  get id() {
    return this._attrs.id || '';
  }
  set id(v) {
    this.setAttribute('id', v);
  }

  get className() {
    return this._attrs.class || '';
  }
  set className(v) {
    this.setAttribute('class', v);
  }

  get title() {
    return this._attrs.title || '';
  }
  set title(v) {
    this.setAttribute('title', v);
  }

  get hidden() {
    return Object.prototype.hasOwnProperty.call(this._attrs, 'hidden');
  }
  set hidden(v) {
    if (v) this._attrs.hidden = '';
    else delete this._attrs.hidden;
  }

  get disabled() {
    return Object.prototype.hasOwnProperty.call(this._attrs, 'disabled');
  }
  set disabled(v) {
    if (v) this._attrs.disabled = '';
    else delete this._attrs.disabled;
  }

  setAttribute(name, value) {
    const key = String(name).toLowerCase();
    const strVal = String(value ?? '');
    this._attrs[key] = strVal;
    if (key === 'style') {
      this.style.cssText = strVal;
    } else if (key === 'value') {
      this.value = strVal;
    } else if (key === 'min') {
      this.min = strVal;
    } else if (key === 'max') {
      this.max = strVal;
    }
  }

  getAttribute(name) {
    const key = String(name).toLowerCase();
    return Object.prototype.hasOwnProperty.call(this._attrs, key) ? this._attrs[key] : null;
  }

  hasAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this._attrs, String(name).toLowerCase());
  }

  removeAttribute(name) {
    delete this._attrs[String(name).toLowerCase()];
  }

  appendChild(node) {
    if (!node) return node;
    if (node.parentNode) node.parentNode.removeChild(node);
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }

  removeChild(node) {
    const idx = this.childNodes.indexOf(node);
    if (idx >= 0) {
      this.childNodes.splice(idx, 1);
      node.parentNode = null;
    }
    return node;
  }

  insertBefore(newNode, refNode) {
    if (!refNode) return this.appendChild(newNode);
    const idx = this.childNodes.indexOf(refNode);
    if (idx === -1) return this.appendChild(newNode);
    if (newNode.parentNode) newNode.parentNode.removeChild(newNode);
    newNode.parentNode = this;
    this.childNodes.splice(idx, 0, newNode);
    return newNode;
  }

  remove() {
    if (this.parentNode) this.parentNode.removeChild(this);
  }

  replaceChildren(...nodes) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    for (const n of nodes) this.appendChild(n);
  }

  get textContent() {
    return this.childNodes
      .map((c) => (c.nodeType === 3 ? c.textContent : c.textContent))
      .join('');
  }

  set textContent(val) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    if (val !== null && val !== undefined && String(val) !== '') {
      this.appendChild(new TextNode(String(val), this.ownerDocument));
    }
  }

  get innerText() {
    return this.textContent;
  }
  set innerText(v) {
    this.textContent = v;
  }

  get innerHTML() {
    return this.childNodes
      .map((c) => (c.nodeType === 3 ? c.textContent : c.outerHTML))
      .join('');
  }

  set innerHTML(html) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    const parsed = buildHtmlNodes(html, this.ownerDocument, this.namespaceURI);
    for (const n of parsed) this.appendChild(n);
  }

  get outerHTML() {
    const tag = this.tagName.toLowerCase();
    const attrParts = [];
    for (const [k, v] of Object.entries(this._attrs)) {
      if (v === '') attrParts.push(k);
      else attrParts.push(`${k}="${String(v).replace(/"/g, '&quot;')}"`);
    }
    const attrStr = attrParts.length ? ' ' + attrParts.join(' ') : '';
    if (VOID_TAGS.has(tag)) {
      return `<${tag}${attrStr} />`;
    }
    return `<${tag}${attrStr}>${this.innerHTML}</${tag}>`;
  }

  matches(selector) {
    return matchesSelector(this, selector);
  }

  closest(selector) {
    let cur = this;
    while (cur && cur.nodeType === 1) {
      if (cur.matches(selector)) return cur;
      cur = cur.parentNode;
    }
    return null;
  }

  querySelectorAll(selector) {
    const out = [];
    const walk = (node) => {
      for (const child of node.childNodes) {
        if (child.nodeType === 1) {
          if (matchesSelector(child, selector)) out.push(child);
          walk(child);
        }
      }
    };
    walk(this);
    return out;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  addEventListener(type, fn) {
    if (typeof fn !== 'function') return;
    if (!this._listeners.has(type)) this._listeners.set(type, new Set());
    this._listeners.get(type).add(fn);
  }

  removeEventListener(type, fn) {
    this._listeners.get(type)?.delete(fn);
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    let cur = this;
    while (cur) {
      event.currentTarget = cur;
      const listeners = cur._listeners?.get(event.type);
      if (listeners) {
        for (const fn of Array.from(listeners)) {
          fn.call(cur, event);
        }
      }
      if (!event.bubbles || event.cancelBubble) break;
      cur = cur.parentNode || (cur === this.ownerDocument.body ? this.ownerDocument : null);
    }
    if (event.bubbles && !event.cancelBubble && cur !== this.ownerDocument) {
      this.ownerDocument.dispatchEvent(event);
    }
    return !event.defaultPrevented;
  }

  click() {
    if (this.disabled) return;
    this.dispatchEvent(new DomEvent('click', { bubbles: true, cancelable: true, target: this }));
  }

  getBoundingClientRect() {
    const win = this.ownerDocument?.defaultView;
    const w = win?.innerWidth || 1280;
    const h = win?.innerHeight || 720;
    return { left: 0, top: 0, width: w, height: h, right: w, bottom: h };
  }

  getContext(type) {
    if (type === '2d') return createMock2DContext();
    if (type === 'webgl2' || type === 'webgl' || type === 'experimental-webgl') {
      return createWebGL2Proxy();
    }
    return null;
  }

  captureStream() {
    return {
      getTracks: () => [{ kind: 'video', stop() {} }],
    };
  }

  getRootNode() {
    return this.ownerDocument || this;
  }

  setPointerCapture() {}
  releasePointerCapture() {}
  focus() {}
  blur() {}

  async play() {}
  pause() {}
  load() {}
}

class DomDocument {
  constructor(defaultView) {
    this.nodeType = 9;
    this.defaultView = defaultView;
    this._listeners = new Map();
    this.hidden = false;
    this.visibilityState = 'visible';
    this.title = 'Smart Home 3D';
    this.documentElement = new DomElement('html', this);
    this.head = new DomElement('head', this);
    this.body = new DomElement('body', this);
    this.documentElement.appendChild(this.head);
    this.documentElement.appendChild(this.body);

    // Base index.html layout
    this.body.innerHTML = `
      <div id="app">
        <div id="canvas-container"></div>
        <div id="css2d-container"></div>
        <div class="ui-layer">
          <header class="top-bar" id="top-bar"></header>
          <aside class="modal-drawer glass" id="device-modal-drawer"></aside>
          <footer class="timeline-bar glass" id="timeline-container"></footer>
        </div>
      </div>
    `;
  }

  createElement(tag) {
    return new DomElement(tag, this, null);
  }
  createElementNS(ns, tag) {
    return new DomElement(tag, this, ns);
  }
  createTextNode(text) {
    return new TextNode(text, this);
  }
  getElementById(id) {
    return this.querySelector(`#${id}`);
  }
  querySelector(sel) {
    return this.documentElement.querySelector(sel);
  }
  querySelectorAll(sel) {
    return this.documentElement.querySelectorAll(sel);
  }
  addEventListener(type, fn) {
    if (!this._listeners.has(type)) this._listeners.set(type, new Set());
    this._listeners.get(type).add(fn);
  }
  removeEventListener(type, fn) {
    this._listeners.get(type)?.delete(fn);
  }
  dispatchEvent(event) {
    event.currentTarget = this;
    const listeners = this._listeners.get(event.type);
    if (listeners) {
      for (const fn of Array.from(listeners)) {
        fn.call(this, event);
      }
    }
    return !event.defaultPrevented;
  }
}

function isElementVisibleAndEnabled(el) {
  if (!el) return false;
  if (el.disabled === true) return false;
  let cur = el;
  while (cur && cur.nodeType === 1) {
    if (cur.hidden === true) return false;
    if (cur.style?.display === 'none') return false;
    if (cur.style?.visibility === 'hidden') return false;
    if (cur.classList?.contains('hidden') || cur.classList?.contains('d-none')) return false;
    if (cur.getAttribute?.('aria-hidden') === 'true') return false;
    cur = cur.parentNode;
  }
  return true;
}

// ============================================================================
// Minimal Valid GLB Builder (for AssetLoader / GLTFLoader tests)
// ============================================================================

function createMinimalGlbArrayBuffer() {
  const jsonText = JSON.stringify({
    asset: { version: '2.0' },
    scene: 0,
    scenes: [{ nodes: [] }],
  });
  let jsonBytes = Buffer.from(jsonText, 'utf8');
  const padLen = (4 - (jsonBytes.length % 4)) % 4;
  if (padLen > 0) {
    jsonBytes = Buffer.concat([jsonBytes, Buffer.alloc(padLen, 0x20)]);
  }
  const totalLen = 12 + 8 + jsonBytes.length;
  const buf = Buffer.alloc(totalLen);
  buf.writeUInt32LE(0x46546c67, 0); // 'glTF'
  buf.writeUInt32LE(2, 4);          // version 2
  buf.writeUInt32LE(totalLen, 8);
  buf.writeUInt32LE(jsonBytes.length, 12);
  buf.writeUInt32LE(0x4e4f534a, 16); // 'JSON'
  jsonBytes.copy(buf, 20);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

// ============================================================================
// Environment & Global Installer
// ============================================================================

function createStorageMock(initial = {}) {
  const map = new Map(Object.entries(initial).map(([k, v]) => [String(k), String(v)]));
  return {
    getItem: (k) => (map.has(String(k)) ? map.get(String(k)) : null),
    setItem: (k, v) => map.set(String(k), String(v)),
    removeItem: (k) => map.delete(String(k)),
    clear: () => map.clear(),
    key: (i) => Array.from(map.keys())[i] ?? null,
    get length() { return map.size; },
    _dump: () => Object.fromEntries(map.entries()),
  };
}

function setupBrowserGlobals(scenario) {
  const locHref = scenario.location || 'https://home.tailnet.ts.net/';
  let parsedUrl = new URL(locHref);
  const locationObj = {
    get href() { return parsedUrl.href; },
    set href(v) { parsedUrl = new URL(v, parsedUrl.origin); },
    get origin() { return parsedUrl.origin; },
    get protocol() { return parsedUrl.protocol; },
    get host() { return parsedUrl.host; },
    get hostname() { return parsedUrl.hostname; },
    get port() { return parsedUrl.port; },
    get pathname() { return parsedUrl.pathname; },
    get search() { return parsedUrl.search; },
    get hash() { return parsedUrl.hash; },
    toString() { return parsedUrl.href; },
  };

  const historyCalls = [];
  const historyObj = {
    replaceState(state, title, url) {
      historyCalls.push({ state, title, url });
      if (url) {
        parsedUrl = new URL(url, parsedUrl.origin);
      }
    },
    pushState(state, title, url) {
      if (url) {
        parsedUrl = new URL(url, parsedUrl.origin);
      }
    },
  };

  const winListeners = new Map();
  const windowObj = {
    Event: DomEvent,
    CustomEvent: class extends DomEvent {
      constructor(type, init = {}) {
        super(type, init);
        this.detail = init.detail;
      }
    },
    location: locationObj,
    history: historyObj,
    innerWidth: scenario.viewport?.width ?? 1280,
    innerHeight: scenario.viewport?.height ?? 720,
    devicePixelRatio: scenario.viewport?.dpr ?? 1,
    addEventListener(type, fn) {
      if (!winListeners.has(type)) winListeners.set(type, new Set());
      winListeners.get(type).add(fn);
    },
    removeEventListener(type, fn) {
      winListeners.get(type)?.delete(fn);
    },
    dispatchEvent(event) {
      const set = winListeners.get(event.type);
      if (set) {
        for (const fn of Array.from(set)) fn(event);
      }
      return true;
    },
    matchMedia(query) {
      const q = String(query || '').toLowerCase();
      const isCoarse = scenario.viewport?.pointer === 'coarse';
      const maxWidthMatch = q.match(/max-width:\s*(\d+)px/);
      let matches = false;
      if (q.includes('pointer: coarse')) matches = isCoarse;
      else if (q.includes('pointer: fine')) matches = !isCoarse;
      else if (q.includes('hover: none')) matches = isCoarse;
      else if (maxWidthMatch) matches = windowObj.innerWidth <= Number(maxWidthMatch[1]);
      return {
        matches,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
      };
    },
  };

  const doc = new DomDocument(windowObj);
  windowObj.document = doc;

  const localStorageMock = createStorageMock(scenario.localStorage || {});
  const sessionStorageMock = createStorageMock(scenario.sessionStorage || {});

  const navigatorMock = {
    userAgent: scenario.userAgent || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    maxTouchPoints: scenario.viewport?.maxTouchPoints ?? 0,
  };
  if (scenario.serviceWorkerSupported !== false) {
    navigatorMock.serviceWorker = {
      register: async () => ({}),
      ready: Promise.resolve({}),
    };
  }

  // Controllable clock & rAF
  let simTimeMs = 10000;
  let nextRafId = 1;
  const rafCallbacks = new Map();

  const perfObj = {
    now: () => simTimeMs,
  };

  const requestAnimationFrameMock = (fn) => {
    const id = nextRafId++;
    rafCallbacks.set(id, fn);
    return id;
  };
  const cancelAnimationFrameMock = (id) => {
    rafCallbacks.delete(id);
  };

  // Optional fake timers
  const realSetTimeout = globalThis.setTimeout;
  const realClearTimeout = globalThis.clearTimeout;
  const realSetInterval = globalThis.setInterval;
  const realClearInterval = globalThis.clearInterval;
  let nextTimerId = 1;
  const activeTimers = new Map();
  const scheduledTimeoutsLog = [];

  if (scenario.fakeTimers) {
    globalThis.setTimeout = (fn, delay = 0, ...args) => {
      const id = nextTimerId++;
      const entry = { id, fn, delay, triggerAt: simTimeMs + delay, args, interval: false };
      activeTimers.set(id, entry);
      scheduledTimeoutsLog.push({ id, delay });
      return id;
    };
    globalThis.clearTimeout = (id) => {
      activeTimers.delete(id);
    };
    globalThis.setInterval = (fn, delay = 0, ...args) => {
      const id = nextTimerId++;
      activeTimers.set(id, { id, fn, delay, triggerAt: simTimeMs + delay, args, interval: true });
      return id;
    };
    globalThis.clearInterval = (id) => {
      activeTimers.delete(id);
    };
  }

  // WebSocket mock
  const wsInstances = [];
  class MockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    constructor(url, protocols) {
      this.url = url;
      this.protocols = protocols;
      this.readyState = MockWebSocket.CONNECTING;
      this.binaryType = 'blob';
      this.sent = [];
      this.closeCalls = [];
      this._listeners = new Map();
      this.seq = ++networkSeq;
      wsInstances.push(this);
      networkEvents.push({ seq: this.seq, type: 'ws', url });
      if (typeof scenario._onWsConstruct === 'function') {
        scenario._onWsConstruct(this);
      }
    }
    addEventListener(type, fn) {
      if (!this._listeners.has(type)) this._listeners.set(type, new Set());
      this._listeners.get(type).add(fn);
    }
    removeEventListener(type, fn) {
      this._listeners.get(type)?.delete(fn);
    }
    _dispatch(type, evt) {
      const handler = this[`on${type}`];
      if (typeof handler === 'function') handler.call(this, evt);
      const set = this._listeners.get(type);
      if (set) {
        for (const fn of Array.from(set)) fn.call(this, evt);
      }
    }
    send(data) {
      this.sent.push(data);
      if (typeof scenario._onWsSend === 'function') {
        scenario._onWsSend(this, data);
      }
    }
    close(code = 1000, reason = '') {
      this.closeCalls.push({ code, reason });
      this.readyState = MockWebSocket.CLOSED;
      this._dispatch('close', { code, reason, wasClean: code === 1000 });
    }
    _triggerOpen() {
      this.readyState = MockWebSocket.OPEN;
      this._dispatch('open', {});
    }
    _triggerMessage(data) {
      this._dispatch('message', { data });
    }
    _triggerClose(code = 1000, reason = '') {
      this.readyState = MockWebSocket.CLOSED;
      this._dispatch('close', { code, reason, wasClean: code === 1000 });
    }
    _triggerError(err = {}) {
      this._dispatch('error', err);
    }
  }

  // RTCPeerConnection & MediaStream mock
  const rtcInstances = [];
  class MockMediaStream {
    constructor() {
      this._tracks = [];
    }
    addTrack(t) { this._tracks.push(t); }
    getTracks() { return this._tracks; }
  }
  class MockRTCPeerConnection {
    constructor(cfg) {
      this.config = cfg;
      this.iceGatheringState = 'complete';
      this.connectionState = 'new';
      this.localDescription = null;
      this.remoteDescription = null;
      this.transceivers = [];
      this._listeners = new Map();
      rtcInstances.push(this);
    }
    addTransceiver(kind, init) {
      this.transceivers.push({ kind, init });
    }
    async createOffer() {
      return { type: 'offer', sdp: 'v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\n' };
    }
    async setLocalDescription(desc) {
      this.localDescription = desc;
    }
    async setRemoteDescription(desc) {
      this.remoteDescription = desc;
      this.connectionState = 'connected';
      if (scenario.rtcEmitTrack !== false && typeof this.ontrack === 'function') {
        this.ontrack({ track: { kind: 'video', stop() {} } });
      }
    }
    addEventListener(t, fn) {
      if (!this._listeners.has(t)) this._listeners.set(t, new Set());
      this._listeners.get(t).add(fn);
    }
    removeEventListener(t, fn) {
      this._listeners.get(t)?.delete(fn);
    }
    close() {
      this.connectionState = 'closed';
    }
  }

  // MediaSource / ManagedMediaSource mock
  const createdMediaSources = [];
  class MockSourceBuffer {
    constructor(mime) {
      this.mime = mime;
      this.mode = 'segments';
      this.updating = false;
      this.appended = [];
      this._listeners = new Map();
    }
    addEventListener(t, fn) {
      if (!this._listeners.has(t)) this._listeners.set(t, new Set());
      this._listeners.get(t).add(fn);
    }
    appendBuffer(chunk) {
      this.appended.push(chunk?.byteLength ?? chunk?.length ?? 0);
      queueMicrotask(() => {
        const set = this._listeners.get('updateend');
        if (set) for (const fn of Array.from(set)) fn({});
      });
    }
  }
  function makeMediaSourceClass(kindName) {
    return class {
      static isTypeSupported() { return true; }
      constructor() {
        this.kindName = kindName;
        this.readyState = 'open';
        this.sourceBuffers = [];
        this._listeners = new Map();
        createdMediaSources.push(this);
      }
      addEventListener(t, fn) {
        if (!this._listeners.has(t)) this._listeners.set(t, new Set());
        this._listeners.get(t).add(fn);
        if (t === 'sourceopen') {
          queueMicrotask(() => fn({}));
        }
      }
      addSourceBuffer(mime) {
        const sb = new MockSourceBuffer(mime);
        this.sourceBuffers.push(sb);
        return sb;
      }
      endOfStream() {
        this.readyState = 'closed';
      }
    };
  }

  // Fetch mock
  const networkEvents = [];
  let networkSeq = 0;
  const fetchLog = [];
  let customFetchHandler = null;
  const mockFetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input?.url || String(input));
    const method = (init?.method || (typeof input === 'object' && input?.method) || 'GET').toUpperCase();
    const headers = {};
    const rawHeaders = init?.headers || {};
    if (rawHeaders instanceof Headers) {
      rawHeaders.forEach((v, k) => { headers[k] = v; });
    } else if (typeof rawHeaders === 'object') {
      for (const [k, v] of Object.entries(rawHeaders)) headers[k] = v;
    }
    const entry = {
      seq: ++networkSeq,
      url,
      method,
      headers,
      credentials: init?.credentials,
      body: init?.body ?? null,
      aborted: false,
    };
    fetchLog.push(entry);
    networkEvents.push({ seq: entry.seq, type: 'fetch', url, method });

    if (init?.signal?.aborted) {
      entry.aborted = true;
      throw new DOMException('Aborted', 'AbortError');
    }

    if (typeof customFetchHandler === 'function') {
      return await customFetchHandler(url, init, entry);
    }

    // Default route table from scenario.fetchRoutes
    if (Array.isArray(scenario.fetchRoutes)) {
      for (const route of scenario.fetchRoutes) {
        const matched = route.exact ? url === route.exact : url.includes(route.match || '');
        if (!matched) continue;
        if (route.hang) {
          return await new Promise((_, reject) => {
            if (init?.signal) {
              init.signal.addEventListener('abort', () => {
                entry.aborted = true;
                const err = new Error('The operation was aborted.');
                err.name = 'AbortError';
                reject(err);
              });
            }
          });
        }
        if (route.reject) {
          throw new Error(route.reject);
        }
        const status = route.status ?? 200;
        const ok = status >= 200 && status < 300;
        const bodyData = route.json !== undefined ? JSON.stringify(route.json) : (route.text ?? '');
        return {
          ok,
          status,
          statusText: route.statusText || (ok ? 'OK' : 'Error'),
          headers: new Map([['content-type', route.contentType || 'application/json']]),
          json: async () => (route.json !== undefined ? route.json : JSON.parse(bodyData)),
          text: async () => bodyData,
          arrayBuffer: async () => (route.glb ? createMinimalGlbArrayBuffer() : Buffer.from(bodyData).buffer),
          blob: async () => new Blob([route.bytes ? new Uint8Array(route.bytes) : bodyData], { type: route.contentType || 'image/jpeg' }),
        };
      }
    }

    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Map([['content-type', 'application/json']]),
      json: async () => ({}),
      text: async () => '',
      arrayBuffer: async () => createMinimalGlbArrayBuffer(),
      blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' }),
    };
  };

  // Install globals
  globalThis.window = windowObj;
  globalThis.self = windowObj;
  globalThis.document = doc;
  globalThis.location = locationObj;
  globalThis.history = historyObj;
  globalThis.localStorage = localStorageMock;
  globalThis.sessionStorage = sessionStorageMock;
  Object.defineProperty(globalThis, 'navigator', { value: navigatorMock, configurable: true, writable: true });
  globalThis.fetch = mockFetch;
  const NativeRequest = globalThis.Request;
  if (NativeRequest) {
    globalThis.Request = class extends NativeRequest {
      constructor(input, init) {
        const resolved = typeof input === 'string' && !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(input)
          ? new URL(input, locationObj.origin).href
          : input;
        super(resolved, init);
      }
    };
  }
  globalThis.WebSocket = MockWebSocket;
  if (scenario.rtcSupported !== false) {
    globalThis.RTCPeerConnection = MockRTCPeerConnection;
    globalThis.MediaStream = MockMediaStream;
  } else {
    delete globalThis.RTCPeerConnection;
  }

  const msMode = scenario.mediaSourceMode || 'standard';
  if (msMode === 'standard') {
    globalThis.MediaSource = makeMediaSourceClass('MediaSource');
    delete globalThis.ManagedMediaSource;
  } else if (msMode === 'ios17') {
    delete globalThis.MediaSource;
    globalThis.ManagedMediaSource = makeMediaSourceClass('ManagedMediaSource');
  } else if (msMode === 'none') {
    delete globalThis.MediaSource;
    delete globalThis.ManagedMediaSource;
  }

  globalThis.requestAnimationFrame = requestAnimationFrameMock;
  globalThis.cancelAnimationFrame = cancelAnimationFrameMock;
  globalThis.performance = perfObj;
  globalThis.Event = DomEvent;
  globalThis.CustomEvent = class extends DomEvent {
    constructor(type, init = {}) {
      super(type, init);
      this.detail = init.detail;
    }
  };
  globalThis.URL = class extends URL {};
  const objectUrls = new Map();
  let objUrlCounter = 1;
  globalThis.URL.createObjectURL = (obj) => {
    const u = `blob:sh3d-mock/${objUrlCounter++}`;
    objectUrls.set(u, obj);
    return u;
  };
  globalThis.URL.revokeObjectURL = (u) => {
    objectUrls.delete(u);
  };
  globalThis.createImageBitmap = async (blob) => ({ width: 640, height: 360, close() {} });
  class MockImage {
    constructor() {
      this._src = '';
      this.width = 128;
      this.height = 128;
      this.complete = true;
      this.onload = null;
      this.onerror = null;
    }
    get src() { return this._src; }
    set src(val) {
      this._src = String(val ?? '');
      queueMicrotask(() => {
        if (typeof this.onload === 'function') this.onload();
      });
    }
  }
  globalThis.Image = MockImage;
  windowObj.Image = MockImage;

  // HA WS mock control structure
  const haWsState = {
    getAuthCalls: [],
    getUserCalls: [],
    createConnectionCalls: [],
    createLongLivedTokenAuthCalls: [],
    revokeCalls: [],
    storedTokensOverride: null,
    user: scenario.mockHaUser || { id: 'u-admin', name: 'Admin', is_admin: true, is_owner: false },
    getAuthBehavior: scenario.getAuthBehavior || 'from_load_tokens',
    connectionShouldFail: Boolean(scenario.connectionShouldFail),
    subscribedCallbacks: [],
  };
  globalThis.__SH3D_TEST_HA_WS__ = haWsState;

  // virtual:pwa-register control structure
  const pwaRegisterState = {
    calls: [],
    lastOptions: null,
    updateSwCalls: [],
    throwOnRegister: Boolean(scenario.throwOnRegisterSw),
  };
  globalThis.__SH3D_TEST_REGISTER_SW__ = (options = {}) => {
    if (pwaRegisterState.throwOnRegister) {
      throw new Error('ServiceWorker registration failed');
    }
    pwaRegisterState.calls.push(options);
    pwaRegisterState.lastOptions = options;
    return async (reloadPage) => {
      pwaRegisterState.updateSwCalls.push(reloadPage);
    };
  };

  return {
    window: windowObj,
    document: doc,
    localStorage: localStorageMock,
    historyCalls,
    fetchLog,
    networkEvents,
    wsInstances,
    rtcInstances,
    createdMediaSources,
    rafCallbacks,
    activeTimers,
    scheduledTimeoutsLog,
    haWsState,
    pwaRegisterState,
    setFetchHandler(fn) { customFetchHandler = fn; },
    stepRaf(advanceMs = 16) {
      simTimeMs += advanceMs;
      const batch = Array.from(rafCallbacks.entries());
      rafCallbacks.clear();
      for (const [, fn] of batch) {
        fn(simTimeMs);
      }
      return batch.length;
    },
    advanceClock(ms) {
      simTimeMs += ms;
      if (scenario.fakeTimers) {
        const due = Array.from(activeTimers.values())
          .filter((t) => t.triggerAt <= simTimeMs)
          .sort((a, b) => a.triggerAt - b.triggerAt);
        for (const t of due) {
          if (!activeTimers.has(t.id)) continue;
          if (t.interval) {
            t.triggerAt += t.delay;
          } else {
            activeTimers.delete(t.id);
          }
          t.fn(...t.args);
        }
      }
    },
    cleanup() {
      globalThis.setTimeout = realSetTimeout;
      globalThis.clearTimeout = realClearTimeout;
      globalThis.setInterval = realSetInterval;
      globalThis.clearInterval = realClearInterval;
    },
  };
}

// ============================================================================
// Vite SSR Server Creation (Zero .env reading)
// ============================================================================

async function createTestViteServer(scenario) {
  const mode = scenario.mode || 'production';
  const envDefaults = {
    MODE: mode,
    PROD: mode === 'production',
    DEV: mode !== 'production',
    SSR: false,
    BASE_URL: '/',
    VITE_HA_TOKEN: '',
    VITE_HA_PUBLIC_URL: '',
    VITE_HA_TAILSCALE_URL: '',
    VITE_HA_LOCAL_URL: '',
    VITE_HA_URL: '',
    VITE_SPATIAL_SERVER_URL: '',
    VITE_GO2RTC_URL: '',
    VITE_GO2RTC_TAILSCALE_URL: '',
  };
  const mergedEnv = { ...envDefaults, ...(scenario.env || {}) };
  const define = {};
  for (const [k, v] of Object.entries(mergedEnv)) {
    define[`import.meta.env.${k}`] = JSON.stringify(v);
  }

  const testEnvPlugin = {
    name: 'sh3d-test-env',
    enforce: 'pre',
    config() {
      return { define };
    },
    configResolved(resolvedConfig) {
      if (resolvedConfig && resolvedConfig.env) {
        Object.assign(resolvedConfig.env, mergedEnv);
      }
    },
  };

  const virtualPwaStubPlugin = {
    name: 'sh3d-virtual-pwa-stub',
    enforce: 'pre',
    resolveId(id) {
      if (id === 'virtual:pwa-register' || id === 'virtual:pwa-register/vanilla') {
        return '\0' + id;
      }
    },
    load(id) {
      if (id === '\0virtual:pwa-register' || id === '\0virtual:pwa-register/vanilla') {
        return `
          export function registerSW(options = {}) {
            if (typeof globalThis.__SH3D_TEST_REGISTER_SW__ === 'function') {
              return globalThis.__SH3D_TEST_REGISTER_SW__(options);
            }
            return async () => {};
          }
        `;
      }
    },
  };

  const haWsMockPlugin = {
    name: 'sh3d-ha-ws-mock',
    enforce: 'pre',
    resolveId(id) {
      if (scenario.mockHaWs !== false && id === 'home-assistant-js-websocket') {
        return '\0mock-ha-ws';
      }
    },
    load(id) {
      if (id === '\0mock-ha-ws') {
        return `
          export const ERR_INVALID_AUTH = 2;
          export const ERR_INVALID_AUTH_CALLBACK = 3;
          export const ERR_INVALID_HTTPS_TO_HTTP = 4;
          export const ERR_HASS_HOST_REQUIRED = 5;
          export const ERR_CANNOT_CONNECT = 1;

          function state() { return globalThis.__SH3D_TEST_HA_WS__; }

          export async function getAuth(options = {}) {
            const s = state();
            s.getAuthCalls.push({ hassUrl: options.hassUrl || null });
            const loaded = typeof options.loadTokens === 'function' ? await options.loadTokens() : null;
            if (s.getAuthBehavior === 'throw_invalid_auth') {
              throw ERR_INVALID_AUTH;
            }
            if (s.getAuthBehavior === 'exchange_callback' || loaded) {
              const tokenData = loaded || {
                hassUrl: options.hassUrl || 'https://home.tailnet.ts.net:8443',
                access_token: 'oauth-token-exchanged',
                refresh_token: 'refresh-tok',
                expires: Date.now() + 1800000,
              };
              if (typeof options.saveTokens === 'function') {
                await options.saveTokens(tokenData);
              }
              return {
                accessToken: tokenData.access_token,
                expired: false,
                data: tokenData,
                async refreshAccessToken() { return tokenData.access_token; },
                async revoke() { s.revokeCalls.push(true); },
              };
            }
            // Simulate redirect
            return {
              accessToken: 'oauth-redirect-token',
              expired: false,
              data: { hassUrl: options.hassUrl, access_token: 'oauth-redirect-token', expires: Date.now() + 1800000 },
              async refreshAccessToken() { return 'oauth-redirect-token'; },
              async revoke() { s.revokeCalls.push(true); },
            };
          }

          export function createLongLivedTokenAuth(hassUrl, accessToken) {
            const s = state();
            s.createLongLivedTokenAuthCalls.push({ hassUrl, accessToken });
            return {
              accessToken,
              expired: false,
              data: { hassUrl, access_token: accessToken },
              async refreshAccessToken() { return accessToken; },
            };
          }

          export async function createConnection({ auth }) {
            const s = state();
            s.createConnectionCalls.push({ hassUrl: auth?.data?.hassUrl, accessToken: auth?.accessToken });
            if (s.connectionShouldFail) {
              throw ERR_CANNOT_CONNECT;
            }
            return {
              addEventListener() {},
              close() {},
              async sendMessagePromise(msg) {
                if (msg?.type === 'auth/current_user') {
                  s.getUserCalls.push(msg);
                  return s.user;
                }
                return {};
              },
              async subscribeMessage() { return () => {}; },
            };
          }

          export async function getUser(conn) {
            return await conn.sendMessagePromise({ type: 'auth/current_user' });
          }

          export function subscribeEntities(conn, cb) {
            const s = state();
            s.subscribedCallbacks.push(cb);
            cb({});
            return () => {};
          }

          export async function callService() {}
        `;
      }
    },
  };

  const plugins = [testEnvPlugin, virtualPwaStubPlugin];
  if (scenario.mockHaWs !== false) {
    plugins.push(haWsMockPlugin);
  }

  return await createServer({
    configFile: false,
    mode,
    envFile: false,
    define,
    optimizeDeps: {
      noDiscovery: true,
      include: [],
    },
    ssr: {
      external: ['lucide'],
      noExternal: ['home-assistant-js-websocket'],
    },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    appType: 'custom',
    logLevel: 'silent',
    plugins,
  });
}

// ============================================================================
// Scenario Dispatcher
// ============================================================================

async function runScenario(scenario) {
  const origConsole = {
    log: console.log,
    info: console.info,
    warn: console.warn,
    error: console.error,
    debug: console.debug,
  };
  const capturedLogs = [];
  console.log = (...args) => capturedLogs.push(['log', args.map(String).join(' ')]);
  console.info = (...args) => capturedLogs.push(['info', args.map(String).join(' ')]);
  console.warn = (...args) => capturedLogs.push(['warn', args.map(String).join(' ')]);
  console.debug = (...args) => capturedLogs.push(['debug', args.map(String).join(' ')]);
  console.error = (...args) => capturedLogs.push(['error', args.map(String).join(' ')]);

  const ctx = setupBrowserGlobals(scenario);
  const server = await createTestViteServer(scenario);
  try {
    const loadModule = (modPath) => server.ssrLoadModule(modPath);

    if (scenario.code) {
      const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
      const fn = new AsyncFunction('ctx', 'loadModule', 'helpers', scenario.code);
      const data = await fn(ctx, loadModule, { isElementVisibleAndEnabled });
      return { ok: true, data };
    }

    const action = scenario.action;

    // ------------------------------------------------------------------------
    // F8 Actions
    // ------------------------------------------------------------------------
    if (action === 'f8_connect') {
      const { HAClient } = await loadModule('/src/ha/HAClient.js');
      const client = new HAClient(scenario.clientOptions || {});
      const statuses = [];
      const authEvents = [];
      client.onStatusChange((status, details) => statuses.push({ status, details }));
      client.onAuthChange((ev) => authEvents.push(ev));

      await client.connect();
      if (scenario.stepAfterConnect === 'logout') {
        await client.logout();
      }
      const accessToken = await client.getAccessToken();
      return {
        ok: true,
        data: {
          isMockMode: client.isMockMode,
          authStatus: client.authStatus,
          currentUser: client.currentUser,
          isAdmin: client.isAdmin,
          activeUrl: client.activeUrl,
          accessToken,
          hasLoginWithOAuth: typeof client.loginWithOAuth === 'function',
          resolvedOAuthUrl: typeof client.resolveOAuthHassUrl === 'function' ? client.resolveOAuthHassUrl() : null,
          statuses,
          authEvents,
          localStorageDump: ctx.localStorage._dump(),
          historyCalls: ctx.historyCalls,
          locationHref: ctx.window.location.href,
          getAuthCalls: ctx.haWsState.getAuthCalls,
          createLongLivedTokenAuthCalls: ctx.haWsState.createLongLivedTokenAuthCalls,
        },
      };
    }

    // ------------------------------------------------------------------------
    // F9 Actions
    // ------------------------------------------------------------------------
    if (action === 'f9_client_check') {
      const { SpatialStreamClient } = await loadModule('/src/spatial/network/SpatialStreamClient.js');
      const client = new SpatialStreamClient(scenario.baseUrl ?? null);

      const frames = [];
      const statuses = [];
      client.onFrame((f) => frames.push(f));
      client.onStatusChange((c, m) => statuses.push({ connected: c, meta: m }));

      let authResult = undefined;
      if (scenario.callAuthWith !== undefined) {
        authResult = await client.authenticateWithHaToken(scenario.callAuthWith);
      }

      let requestResult = undefined;
      if (scenario.requestCall) {
        requestResult = await client.requestJson(scenario.requestCall.path, scenario.requestCall.options || {});
      }

      let statusResult = undefined;
      if (scenario.callFetchStatus) {
        statusResult = await client.fetchStatus();
      }

      if (scenario.testWs) {
        ctx.scheduledTimeoutsLog.length = 0;
        client.connectWebSocket();
        const ws1 = ctx.wsInstances[0];
        if (ws1) {
          ws1._triggerOpen();
          if (scenario.wsMessages) {
            for (const msg of scenario.wsMessages) {
              ws1._triggerMessage(JSON.stringify(msg));
            }
          }
          if (scenario.wsCloseCode !== undefined) {
            ws1._triggerClose(scenario.wsCloseCode, scenario.wsCloseReason || '');
            ctx.advanceClock(20000);
          }
        }
      }

      return {
        ok: true,
        data: {
          baseUrl: client.baseUrl,
          wsUrl: client.wsUrl,
          connected: client.connected,
          authResult,
          requestResult,
          statusResult,
          frames,
          statuses,
          fetchLog: ctx.fetchLog,
          wsCount: ctx.wsInstances.length,
          wsUrls: ctx.wsInstances.map((w) => w.url),
          scheduledTimeoutsCount: ctx.scheduledTimeoutsLog.length,
        },
      };
    }

    // ------------------------------------------------------------------------
    // F10 Actions
    // ------------------------------------------------------------------------
    if (action === 'f10_video_check') {
      const { VideoStreamManager } = await loadModule('/src/video/VideoStreamManager.js');
      const { Go2RtcWebRTCStream } = await loadModule('/src/video/Go2RtcWebRTCStream.js');
      const { Go2RtcMSEStream } = await loadModule('/src/video/Go2RtcMSEStream.js');
      const { HaSnapshotFallbackStream } = await loadModule('/src/video/HaSnapshotFallbackStream.js');

      const videoEl = ctx.document.createElement('video');
      const haClientMock = scenario.haClient || {
        isMockMode: false,
        isTailscale: false,
        resolveCameraEntityId: () => 'camera.carraio_scorrevole',
        getActiveUrl: () => 'https://home.tailnet.ts.net:8443',
        getAccessToken: async () => 'ha-bearer-token-123',
      };

      if (scenario.target === 'manager_init') {
        const mgr = new VideoStreamManager({ haClient: haClientMock });
        return { ok: true, data: { go2rtcUrl: mgr.go2rtcUrl } };
      }

      if (scenario.target === 'manager_fallback') {
        const mgr = new VideoStreamManager({ haClient: haClientMock });
        const provider = await mgr.attachToVideoElement('carraio_main', videoEl, 'auto');
        const mode = provider.mode;
        const providerName = provider.constructor.name;
        provider.disconnect();
        return { ok: true, data: { mode, providerName, fetchLog: ctx.fetchLog } };
      }

      if (scenario.target === 'webrtc') {
        const stream = new Go2RtcWebRTCStream('carraio_main', {
          go2rtcUrl: scenario.go2rtcUrl,
          ...(scenario.timeoutMs ? { timeoutMs: scenario.timeoutMs } : {}),
        });
        const defaultTimeoutMs = stream.timeoutMs;
        let connectedPromise = stream.connect(videoEl);
        if (scenario.hangAndAdvanceMs) {
          // Let createOffer + waitForIceGathering resolve via microtasks before advancing abort timer
          for (let i = 0; i < 15; i++) await Promise.resolve();
          ctx.advanceClock(scenario.hangAndAdvanceMs);
          for (let i = 0; i < 15; i++) await Promise.resolve();
        }
        const ok = await connectedPromise;
        const hasSrcObject = Boolean(videoEl.srcObject);
        stream.disconnect();
        return {
          ok: true,
          data: {
            defaultTimeoutMs,
            connected: ok,
            hasSrcObject,
            fetchLog: ctx.fetchLog,
            lastError: stream.lastError,
          },
        };
      }

      if (scenario.target === 'mse') {
        const stream = new Go2RtcMSEStream('carraio_main', {
          go2rtcUrl: scenario.go2rtcUrl || 'https://home.tailnet.ts.net/go2rtc',
        });
        const connectPromise = stream.connect(videoEl);
        for (let i = 0; i < 10; i++) await Promise.resolve();
        const ws = ctx.wsInstances[0];
        if (ws) {
          ws._triggerOpen();
          ws._triggerMessage(JSON.stringify({ type: 'mse', value: 'video/mp4; codecs="avc1.640029"' }));
          ws._triggerMessage(new Uint8Array([0, 0, 0, 8, 102, 116, 121, 112]).buffer);
        }
        const ok = await connectPromise;
        const usedManaged = ctx.createdMediaSources.some((m) => m.kindName === 'ManagedMediaSource');
        const disableRemotePlayback = videoEl.disableRemotePlayback;
        const wsSent = ws ? ws.sent : [];
        const appended = ctx.createdMediaSources[0]?.sourceBuffers[0]?.appended || [];
        stream.disconnect();
        return {
          ok: true,
          data: {
            connected: ok,
            usedManaged,
            disableRemotePlayback,
            wsUrls: ctx.wsInstances.map((w) => w.url),
            wsSent,
            appended,
          },
        };
      }

      if (scenario.target === 'snapshot') {
        const stream = new HaSnapshotFallbackStream('carraio_main', {
          haClient: haClientMock,
        });
        const ok = await stream.connect(videoEl);
        for (let i = 0; i < 15; i++) await Promise.resolve();
        const status = stream.getStatus();
        stream.disconnect();
        return {
          ok: true,
          data: {
            connected: ok,
            fetchLog: ctx.fetchLog,
            status,
          },
        };
      }
    }

    // ------------------------------------------------------------------------
    // F11 Actions
    // ------------------------------------------------------------------------
    if (action === 'f11_rbac_ui') {
      if (scenario.target === 'topbar') {
        const { TopBar } = await loadModule('/src/ui/TopBar.js');
        const authListeners = new Set();
        const statusListeners = new Set();
        let logoutCalled = false;
        const haClientMock = {
          isAdmin: Boolean(scenario.initialIsAdmin),
          currentUser: scenario.initialUser ?? (scenario.initialIsAdmin ? { id: 'u1', name: 'Admin', is_admin: true } : { id: 'u2', name: 'Mario', is_admin: false }),
          authStatus: scenario.initialUser === null ? 'auth_required' : 'authenticated',
          onStatusChange(fn) { statusListeners.add(fn); return () => statusListeners.delete(fn); },
          onAuthChange(fn) { authListeners.add(fn); return () => authListeners.delete(fn); },
          async logout() { logoutCalled = true; },
        };
        const topBarEl = ctx.document.getElementById('top-bar');
        const topBar = new TopBar(topBarEl, {
          sceneManager: { isNightMode: false, setNightMode() {} },
          cameraController: { flyToPreset() {}, flyToCameraPOV() {} },
          cameraProjector: { toggleFrustums: () => false },
          interactionManager: { toggleBadges: () => false },
          haClient: haClientMock,
          calibrationAssistant: { isOpen: false, open() {}, close() {} },
        });

        const snapshotState = () => {
          const calibBtn = ctx.document.getElementById('btn-open-cam-calib');
          const text = topBarEl.textContent;
          const logoutBtn = topBarEl.querySelector('#btn-ha-logout, #btn-logout, [data-action="logout"], button[id*="logout" i]')
            || topBarEl.querySelectorAll('button').find((b) => /esci|logout/i.test(b.textContent));
          const loginBtn = topBarEl.querySelector('#btn-ha-login, [data-action="login"], button[id*="login" i]')
            || topBarEl.querySelectorAll('button').find((b) => /accedi|login/i.test(b.textContent));
          return {
            calibExists: Boolean(calibBtn),
            calibVisibleAndEnabled: isElementVisibleAndEnabled(calibBtn),
            text,
            hasLogoutBtn: Boolean(logoutBtn && isElementVisibleAndEnabled(logoutBtn)),
            hasLoginBtn: Boolean(loginBtn && isElementVisibleAndEnabled(loginBtn)),
            logoutBtn,
          };
        };

        const states = [snapshotState()];
        if (Array.isArray(scenario.transitions)) {
          for (const tr of scenario.transitions) {
            haClientMock.isAdmin = Boolean(tr.isAdmin);
            haClientMock.currentUser = tr.user ?? null;
            haClientMock.authStatus = tr.status || (tr.user ? 'authenticated' : 'auth_required');
            for (const cb of authListeners) {
              cb({
                authenticated: Boolean(tr.user),
                status: haClientMock.authStatus,
                user: haClientMock.currentUser,
                isAdmin: haClientMock.isAdmin,
                isMockMode: false,
                token: tr.token || null,
              });
            }
            states.push(snapshotState());
          }
        }
        if (scenario.clickLogout) {
          const last = states[states.length - 1];
          last.logoutBtn?.click();
          for (let i = 0; i < 5; i++) await Promise.resolve();
        }
        return {
          ok: true,
          data: {
            states: states.map(({ logoutBtn, ...rest }) => rest),
            logoutCalled,
          },
        };
      }

      if (scenario.target === 'camera_modal') {
        const { SecurityCameraModal } = await loadModule('/src/devices/camera/SecurityCameraModal.js');
        const haClientMock = {
          isAdmin: Boolean(scenario.isAdmin),
          isTailscale: false,
          currentUser: { id: 'u', name: 'User', is_admin: Boolean(scenario.isAdmin) },
        };
        const controllerMock = {
          haClient: haClientMock,
          spatialStreamClient: { fetchStatus: async () => ({ ingestion_mode: 'synthetic' }) },
          videoStreamManager: {
            attachToVideoElement: async () => ({ mode: 'snapshot', getStatus: () => ({ mode: 'snapshot', connected: true, latencyMs: 50 }), onStatusChange: () => () => {} }),
            detachFromVideoElement() {},
          },
          cameraController: { flyToCameraPOV() {} },
          calibrationAssistant: { open() {} },
          findMatchingBlenderCameraName: () => 'Cam_Carraio',
        };
        const modal = new SecurityCameraModal(controllerMock);
        const container = ctx.document.getElementById('device-modal-drawer');
        await modal.render(container, { haClient: haClientMock, assetLoader: { manifest: { cameras: {} }, cameras: new Map() } });

        const calibBtn = container.querySelector('#btn-camera-calibrate');
        const simBtn = container.querySelector('#btn-toggle-simulator');
        const povBtn = container.querySelector('#btn-camera-pov');
        const videoEl = container.querySelector('#cam-modal-video');
        return {
          ok: true,
          data: {
            calibVisibleAndEnabled: isElementVisibleAndEnabled(calibBtn),
            simVisibleAndEnabled: isElementVisibleAndEnabled(simBtn),
            povExists: Boolean(povBtn),
            videoExists: Boolean(videoEl),
          },
        };
      }

      if (scenario.target === 'calibration_guard') {
        const { CalibrationAssistantUI } = await loadModule('/src/spatial/calibration/CalibrationAssistantUI.js');
        let acquireCalled = false;
        const calib = new CalibrationAssistantUI({
          sceneManager: { renderer: { domElement: ctx.document.createElement('canvas') }, addUpdateCallback() {}, removeUpdateCallback() {} },
          cameraController: { setInstantCameraPose() {} },
          cameraProjector: { applyCameraCalibration() {}, attachOverlayTexture() {}, setOverlayPOVMode() {}, setOverlayOpacity() {} },
          videoStreamManager: { acquireVideoTexture: async () => { acquireCalled = true; return { texture: {} }; }, releaseVideoTexture() {} },
          spatialStreamClient: {},
          assetLoader: { manifest: { cameras: {} } },
          haClient: { isAdmin: Boolean(scenario.isAdmin) },
        });
        if ('haClient' in calib === false) {
          calib.haClient = { isAdmin: Boolean(scenario.isAdmin) };
        }
        await calib.open('Cam_Carraio');
        const panel = ctx.document.getElementById('calibration-assistant-panel');
        return {
          ok: true,
          data: {
            isOpen: calib.isOpen,
            panelOpen: Boolean(panel && panel.classList.contains('open')),
            acquireCalled,
          },
        };
      }

      if (scenario.target === 'icons') {
        const { icon } = await loadModule('/src/ui/icons.js');
        const names = scenario.names || [];
        const results = {};
        for (const n of names) {
          results[n] = icon(n, { size: 16 });
        }
        return { ok: true, data: { results } };
      }

      if (scenario.target === 'main_bootstrap') {
        await loadModule('/src/main.js');
        ctx.window.dispatchEvent(new ctx.window.Event('DOMContentLoaded'));
        for (let i = 0; i < 40; i++) {
          await new Promise((r) => setTimeout(r, 5));
        }
        const bodyText = ctx.document.body.textContent;
        const buttons = ctx.document.querySelectorAll('button');
        const loginBtn = buttons.find((b) => /accedi con home assistant/i.test(b.textContent));
        let loginRedirectTriggered = false;
        if (loginBtn && scenario.clickLogin) {
          loginBtn.click();
          for (let i = 0; i < 10; i++) await Promise.resolve();
          loginRedirectTriggered = ctx.haWsState.getAuthCalls.length > 0;
        }
        return {
          ok: true,
          data: {
            bodyText,
            hasLoginOverlay: /accedi con home assistant/i.test(bodyText) && Boolean(loginBtn && isElementVisibleAndEnabled(loginBtn)),
            loginRedirectTriggered,
            fetchLog: ctx.fetchLog,
            networkEvents: ctx.networkEvents,
            wsUrls: ctx.wsInstances.map((w) => w.url),
          },
        };
      }
    }

    // ------------------------------------------------------------------------
    // F13 Actions
    // ------------------------------------------------------------------------
    if (action === 'f13_pwa_prompt') {
      const mod = await loadModule('/src/ui/PwaUpdatePrompt.js');
      let instance = null;
      if (mod.PwaUpdatePrompt) {
        instance = new mod.PwaUpdatePrompt();
        if (ctx.pwaRegisterState.calls.length === 0) {
          if (typeof instance.init === 'function') await instance.init();
          else if (typeof instance.register === 'function') await instance.register();
          else if (typeof instance.mount === 'function') await instance.mount();
        }
      } else {
        const fn = mod.initPwaUpdatePrompt || mod.setupPwaUpdatePrompt || mod.registerPwaUpdatePrompt || mod.default;
        if (typeof fn === 'function') {
          instance = await fn();
        }
      }

      const opts = ctx.pwaRegisterState.lastOptions || {};
      if (scenario.triggerNeedRefresh && typeof opts.onNeedRefresh === 'function') {
        opts.onNeedRefresh();
        if (scenario.repeatNeedRefresh) {
          opts.onNeedRefresh();
        }
      }

      const findButtons = () => ctx.document.querySelectorAll('button');
      const countToasts = () => {
        const all = ctx.document.querySelectorAll('[class*="pwa"], [id*="pwa"], [role="alert"], [role="status"]');
        return all.filter((el) => /nuova versione disponibile/i.test(el.textContent) && isElementVisibleAndEnabled(el)).length;
      };

      const visibleToastBeforeAction = /nuova versione disponibile/i.test(ctx.document.body.textContent);
      const toastCount = countToasts();
      const aggiornaBtn = findButtons().find((b) => /aggiorna/i.test(b.textContent));
      const dismissBtn = findButtons().find((b) =>
        b !== aggiornaBtn &&
        (/ignora|chiudi|dopo|più tardi|later|dismiss|×/i.test(b.textContent) ||
          /chiudi|ignora|dismiss|close/i.test(b.getAttribute('aria-label') || '') ||
          /close|dismiss/i.test(b.className))
      );

      if (scenario.click === 'aggiorna' && aggiornaBtn) {
        aggiornaBtn.click();
        for (let i = 0; i < 5; i++) await Promise.resolve();
      } else if (scenario.click === 'dismiss' && dismissBtn) {
        dismissBtn.click();
        for (let i = 0; i < 5; i++) await Promise.resolve();
      }

      const visibleToastAfterAction = countToasts() > 0;

      return {
        ok: true,
        data: {
          registerCalls: ctx.pwaRegisterState.calls.length,
          visibleToastBeforeAction,
          toastCount,
          hasAggiornaBtn: Boolean(aggiornaBtn),
          hasDismissBtn: Boolean(dismissBtn),
          visibleToastAfterAction,
          updateSwCalls: ctx.pwaRegisterState.updateSwCalls,
          bodyText: ctx.document.body.textContent,
        },
      };
    }

    // ------------------------------------------------------------------------
    // F14 Actions
    // ------------------------------------------------------------------------
    if (action === 'f14_asset_loader') {
      const { AssetLoader } = await loadModule('/src/core/AssetLoader.js');
      const loader = new AssetLoader();
      await loader.loadHouseModel(scenario.modelUrl || '/models/house_optimized.glb');
      const urls = ctx.fetchLog.map((e) => e.url);
      let secondUrls = null;
      if (scenario.secondLoad) {
        ctx.fetchLog.length = 0;
        const loader2 = new AssetLoader();
        if (scenario.secondManifest !== undefined) {
          ctx.setFetchHandler(async (url) => {
            if (url.includes('scene_manifest.json')) {
              return {
                ok: true,
                status: 200,
                json: async () => scenario.secondManifest,
                text: async () => JSON.stringify(scenario.secondManifest),
              };
            }
            return {
              ok: true,
              status: 200,
              arrayBuffer: async () => createMinimalGlbArrayBuffer(),
            };
          });
        }
        await loader2.loadHouseModel(scenario.modelUrl || '/models/house_optimized.glb');
        secondUrls = ctx.fetchLog.map((e) => e.url);
      }
      return { ok: true, data: { urls, secondUrls } };
    }

    if (action === 'f14_scene_manager') {
      const { SceneManager } = await loadModule('/src/core/SceneManager.js');
      const canvasContainer = ctx.document.getElementById('canvas-container');
      const css2dContainer = ctx.document.getElementById('css2d-container');
      const sm = new SceneManager(canvasContainer, css2dContainer);

      const deltas = [];
      sm.addUpdateCallback((delta) => deltas.push(delta));

      // Initial visible step
      ctx.stepRaf(16);
      const initialPixelRatio = sm.renderer.getPixelRatio();
      const initialShadowSize = {
        width: sm.sunLight.shadow.mapSize.width,
        height: sm.sunLight.shadow.mapSize.height,
      };
      const initialRafCount = ctx.rafCallbacks.size;

      // Resize check if requested
      let pixelRatioAfterResize = initialPixelRatio;
      if (scenario.triggerResize) {
        ctx.window.dispatchEvent(new ctx.window.Event('resize'));
        pixelRatioAfterResize = sm.renderer.getPixelRatio();
      }

      let hiddenRafCount = null;
      let ticksWhileHidden = 0;
      let resumedRafCount = null;
      let resumedFirstDelta = null;
      let rapidToggleRafCount = null;

      if (scenario.testVisibility) {
        ctx.document.hidden = true;
        ctx.document.visibilityState = 'hidden';
        ctx.document.dispatchEvent(new ctx.window.Event('visibilitychange'));
        // Step one pending rAF if any was queued before hiding
        const beforeTicks = deltas.length;
        ctx.stepRaf(16);
        ctx.stepRaf(16);
        hiddenRafCount = ctx.rafCallbacks.size;
        ticksWhileHidden = deltas.length - beforeTicks;

        // Simulate 5-second background pause
        ctx.advanceClock(5000);
        ctx.document.hidden = false;
        ctx.document.visibilityState = 'visible';
        ctx.document.dispatchEvent(new ctx.window.Event('visibilitychange'));
        resumedRafCount = ctx.rafCallbacks.size;

        const beforeResume = deltas.length;
        ctx.stepRaf(16);
        resumedFirstDelta = deltas.length > beforeResume ? deltas[beforeResume] : null;
      }

      if (scenario.testRapidToggle) {
        for (const h of [true, false, true, false, true, false]) {
          ctx.document.hidden = h;
          ctx.document.visibilityState = h ? 'hidden' : 'visible';
          ctx.document.dispatchEvent(new ctx.window.Event('visibilitychange'));
        }
        rapidToggleRafCount = ctx.rafCallbacks.size;
      }

      return {
        ok: true,
        data: {
          initialPixelRatio,
          pixelRatioAfterResize,
          initialShadowSize,
          initialRafCount,
          hiddenRafCount,
          ticksWhileHidden,
          resumedRafCount,
          resumedFirstDelta,
          rapidToggleRafCount,
        },
      };
    }

    throw new Error(`Unknown js_harness action: ${action}`);
  } finally {
    console.log = origConsole.log;
    console.info = origConsole.info;
    console.warn = origConsole.warn;
    console.debug = origConsole.debug;
    console.error = origConsole.error;
    ctx.cleanup();
    server.close().catch(() => {});
  }
}

async function main() {
  let rawInput = '';
  if (process.argv[2]) {
    rawInput = fs.readFileSync(path.resolve(process.argv[2]), 'utf8');
  } else {
    const chunks = [];
    for await (const chunk of process.stdin) {
      chunks.push(chunk);
    }
    rawInput = Buffer.concat(chunks).toString('utf8');
  }

  const scenario = JSON.parse(rawInput || '{}');
  const result = await runScenario(scenario);
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: err?.message || String(err),
    stack: err?.stack || '',
  }));
  process.exit(0);
});
