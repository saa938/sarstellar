// WebGL2 renderer for the dance floor. All pass positions live in one RG16F texture
// (texel t * K + k), so moving 100k+ dots between beats is a single uniform change: the vertex
// shader fetches both beats and interpolates. Dots and trails accumulate additively in a
// half-float buffer and are tone-mapped, so dense clusters glow instead of clipping.

export interface FloorView {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
}

export interface DrawParams {
  i0: number;
  i1: number;
  e: number;
  head: number;
  view: FloorView;
  selActive: boolean;
  pointPx: number; // CSS px
  gain: number;
  exposure: number;
  dimOthers: number; // brightness of unselected dots when a selection exists
  hoverK: number;
}

const POINT_VS = `#version 300 es
precision highp float;
precision highp int;
uniform highp sampler2D uPos;
uniform highp sampler2D uState;
uniform int uK;
uniform int uW;
uniform int uI0;
uniform int uI1;
uniform float uE;
uniform vec4 uView;
uniform float uSize;
uniform float uSel;
uniform float uDim;
uniform int uHover;
out vec4 vColor;
ivec2 at(int i) { return ivec2(i % uW, i / uW); }
void main() {
  int k = gl_VertexID;
  vec2 p0 = texelFetch(uPos, at(uI0 * uK + k), 0).rg;
  vec2 p1 = texelFetch(uPos, at(uI1 * uK + k), 0).rg;
  vec2 p = mix(p0, p1, uE);
  vec4 st = texelFetch(uState, at(k), 0);
  int f = int(st.a * 255.0 + 0.5);
  bool sel = (f & 1) != 0;
  bool hi = (f & 2) != 0;
  bool hidden = (f & 4) != 0;
  vec2 ndc = vec2((p.x - uView.x) / (uView.y - uView.x), (p.y - uView.z) / (uView.w - uView.z)) * 2.0 - 1.0;
  gl_Position = vec4(ndc, 0.0, 1.0);
  float size = uSize;
  float a = 1.0;
  if (uSel > 0.5) {
    if (sel) { size *= 1.35; a = 1.25; }
    else { a = uDim; size *= 0.9; }
  }
  if (hi) { size *= 1.6; a = max(a, 1.4); }
  if (k == uHover) { size *= 2.4; a = 3.0; }
  if (hidden) { a = 0.0; size = 0.0; }
  gl_PointSize = size;
  vColor = vec4(st.rgb, a);
}`;

const POINT_FS = `#version 300 es
precision highp float;
in vec4 vColor;
uniform float uGain;
out vec4 o;
void main() {
  vec2 d = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(d, d);
  if (r2 > 1.0) discard;
  float g = exp(-r2 * 4.0) * (1.0 - r2);
  float a = g * vColor.a * uGain;
  o = vec4(vColor.rgb * a, a);
}`;

const TRAIL_VS = `#version 300 es
precision highp float;
precision highp int;
layout(location = 0) in int aK;
layout(location = 1) in int aSeg;
uniform highp sampler2D uPos;
uniform highp sampler2D uState;
uniform int uK;
uniform int uW;
uniform vec4 uView;
uniform vec2 uRes;
uniform float uWidth;
out float vTime;
out float vSide;
out vec3 vColor;
ivec2 at(int i) { return ivec2(i % uW, i / uW); }
vec2 toPx(vec2 p) {
  return vec2((p.x - uView.x) / (uView.y - uView.x), (p.y - uView.z) / (uView.w - uView.z)) * uRes;
}
void main() {
  vec2 p0 = texelFetch(uPos, at(aSeg * uK + aK), 0).rg;
  vec2 p1 = texelFetch(uPos, at((aSeg + 1) * uK + aK), 0).rg;
  vec2 s0 = toPx(p0);
  vec2 s1 = toPx(p1);
  vec2 d = s1 - s0;
  float len = length(d);
  vec2 dir = len > 1e-4 ? d / len : vec2(1.0, 0.0);
  vec2 nrm = vec2(-dir.y, dir.x);
  int vid = gl_VertexID;
  float a = float(vid / 2);
  float side = (vid % 2 == 0) ? -1.0 : 1.0;
  vec2 s = mix(s0, s1, a) + nrm * side * uWidth * 0.5 + dir * (a * 2.0 - 1.0) * uWidth * 0.5;
  gl_Position = vec4(s / uRes * 2.0 - 1.0, 0.0, 1.0);
  vTime = float(aSeg) + a;
  vSide = side;
  vColor = texelFetch(uState, at(aK), 0).rgb;
}`;

const TRAIL_FS = `#version 300 es
precision highp float;
in float vTime;
in float vSide;
in vec3 vColor;
uniform float uHead;
uniform float uTau;
uniform float uGain;
uniform float uFuture;
uniform vec3 uTint;
uniform float uUseTint;
out vec4 o;
void main() {
  float dt = uHead - vTime;
  float a = dt >= 0.0 ? (0.16 + 0.84 * exp(-dt / uTau)) : uFuture * exp(dt / 6.0);
  a *= 1.0 - smoothstep(0.35, 1.0, abs(vSide));
  a *= uGain;
  vec3 c = mix(vColor, uTint, uUseTint);
  o = vec4(c * a, a);
}`;

const COMP_VS = `#version 300 es
out vec2 vUv;
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const COMP_FS = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uHdr;
uniform float uExposure;
uniform vec2 uTexel;
uniform float uBloom;
out vec4 o;
void main() {
  vec3 h = texture(uHdr, vUv).rgb;
  // soft bloom: two rings of taps around the pixel
  vec3 b = vec3(0.0);
  for (int i = 0; i < 8; i++) {
    float an = float(i) * 0.785398;
    vec2 d = vec2(cos(an), sin(an));
    b += texture(uHdr, vUv + d * uTexel * 3.0).rgb * 0.6;
    b += texture(uHdr, vUv + d * uTexel * 7.0).rgb * 0.4;
  }
  h += b / 8.0 * uBloom;
  vec3 c = 1.0 - exp(-h * uExposure);
  float a = max(max(c.r, c.g), c.b);
  o = vec4(c, a);
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(s);
    gl.deleteShader(s);
    throw new Error(`shader: ${log}`);
  }
  return s;
}

function program(gl: WebGL2RenderingContext, vs: string, fs: string) {
  const p = gl.createProgram()!;
  gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs));
  gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(`link: ${gl.getProgramInfoLog(p)}`);
  const u: Record<string, WebGLUniformLocation | null> = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS) as number;
  for (let i = 0; i < n; i++) {
    const info = gl.getActiveUniform(p, i);
    if (info) u[info.name] = gl.getUniformLocation(p, info.name);
  }
  return { p, u };
}

interface TrailSet {
  vao: WebGLVertexArrayObject;
  bufK: WebGLBuffer;
  bufS: WebGLBuffer;
  count: number;
  gain: number;
  width: number;
  tau: number;
  future: number;
  tint: [number, number, number] | null;
}

export class FloorGL {
  readonly canvas: HTMLCanvasElement;
  readonly gl: WebGL2RenderingContext;
  private pts;
  private trail;
  private comp;
  private vaoEmpty: WebGLVertexArrayObject;
  private posTex: WebGLTexture | null = null;
  private stateTex: WebGLTexture | null = null;
  private W = 2048;
  private K = 0;
  private T = 0;
  private hdr = false;
  private fbo: WebGLFramebuffer | null = null;
  private fboTex: WebGLTexture | null = null;
  private fbw = 0;
  private fbh = 0;
  private trails = new Map<string, TrailSet>();
  private cssW = 1;
  private cssH = 1;
  private dpr = 1;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: false, preserveDrawingBuffer: false });
    if (!gl) throw new Error("WebGL2 is not available");
    this.gl = gl;
    this.hdr = !!gl.getExtension("EXT_color_buffer_float") || !!gl.getExtension("EXT_color_buffer_half_float");
    this.pts = program(gl, POINT_VS, POINT_FS);
    this.trail = program(gl, TRAIL_VS, TRAIL_FS);
    this.comp = program(gl, COMP_VS, COMP_FS);
    this.vaoEmpty = gl.createVertexArray()!;
    const max = gl.getParameter(gl.MAX_TEXTURE_SIZE) as number;
    this.W = Math.min(4096, max);
  }

  get count() {
    return this.K;
  }

  setData(xy: Float32Array, T: number, K: number) {
    const gl = this.gl;
    this.T = T;
    this.K = K;
    const total = T * K;
    const W = this.W;
    const H = Math.max(1, Math.ceil(total / W));
    if (this.posTex) gl.deleteTexture(this.posTex);
    const tex = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RG16F, W, H);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    const fullRows = Math.floor(total / W);
    if (fullRows > 0) gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, W, fullRows, gl.RG, gl.FLOAT, xy.subarray(0, fullRows * W * 2));
    const rem = total - fullRows * W;
    if (rem > 0) gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, fullRows, rem, 1, gl.RG, gl.FLOAT, xy.subarray(fullRows * W * 2, total * 2));
    this.texParams();
    this.posTex = tex;
  }

  /** rgba per block: rgb color, a = flags (1 selected, 2 highlighted, 4 hidden). */
  setState(rgba: Uint8Array) {
    const gl = this.gl;
    const W = this.W;
    const H = Math.max(1, Math.ceil(this.K / W));
    let data = rgba;
    if (rgba.length < W * H * 4) {
      data = new Uint8Array(W * H * 4);
      data.set(rgba);
    }
    if (!this.stateTex) {
      this.stateTex = gl.createTexture()!;
      gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, W, H, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
      this.texParams();
      this.stateH = H;
    } else {
      gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
      if (this.stateH !== H) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, W, H, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
        this.stateH = H;
      } else gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, data);
    }
  }
  private stateH = 0;

  private texParams() {
    const gl = this.gl;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  setTrails(name: string, ks: ArrayLike<number>, opts: { gain: number; width: number; tau?: number; future?: number; tint?: [number, number, number] | null }) {
    const gl = this.gl;
    let ts = this.trails.get(name);
    const segs = Math.max(0, this.T - 1);
    const count = ks.length * segs;
    const K = new Int32Array(count);
    const S = new Int32Array(count);
    let o = 0;
    for (let j = 0; j < ks.length; j++) {
      for (let s = 0; s < segs; s++) {
        K[o] = ks[j];
        S[o] = s;
        o++;
      }
    }
    if (!ts) {
      const vao = gl.createVertexArray()!;
      const bufK = gl.createBuffer()!;
      const bufS = gl.createBuffer()!;
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, bufK);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribIPointer(0, 1, gl.INT, 0, 0);
      gl.vertexAttribDivisor(0, 1);
      gl.bindBuffer(gl.ARRAY_BUFFER, bufS);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribIPointer(1, 1, gl.INT, 0, 0);
      gl.vertexAttribDivisor(1, 1);
      gl.bindVertexArray(null);
      ts = { vao, bufK, bufS, count: 0, gain: 1, width: 1.5, tau: 3, future: 0.08, tint: null };
      this.trails.set(name, ts);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, ts.bufK);
    gl.bufferData(gl.ARRAY_BUFFER, K, gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, ts.bufS);
    gl.bufferData(gl.ARRAY_BUFFER, S, gl.DYNAMIC_DRAW);
    ts.count = count;
    ts.gain = opts.gain;
    ts.width = opts.width;
    ts.tau = opts.tau ?? 3;
    ts.future = opts.future ?? 0.08;
    ts.tint = opts.tint ?? null;
  }

  resize(cssW: number, cssH: number, dpr: number) {
    this.cssW = Math.max(1, cssW);
    this.cssH = Math.max(1, cssH);
    this.dpr = dpr;
    const w = Math.max(1, Math.round(cssW * dpr));
    const h = Math.max(1, Math.round(cssH * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    if (this.hdr && (this.fbw !== w || this.fbh !== h)) this.makeFbo(w, h);
  }

  private makeFbo(w: number, h: number) {
    const gl = this.gl;
    if (this.fbo) gl.deleteFramebuffer(this.fbo);
    if (this.fboTex) gl.deleteTexture(this.fboTex);
    const tex = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fbo = gl.createFramebuffer()!;
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!ok) {
      gl.deleteFramebuffer(fbo);
      gl.deleteTexture(tex);
      this.hdr = false;
      this.fbo = null;
      this.fboTex = null;
      return;
    }
    this.fbo = fbo;
    this.fboTex = tex;
    this.fbw = w;
    this.fbh = h;
  }

  draw(p: DrawParams) {
    const gl = this.gl;
    if (!this.posTex || !this.stateTex || this.K === 0) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, this.canvas.width, this.canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      return;
    }
    const w = this.canvas.width;
    const h = this.canvas.height;
    const useHdr = this.hdr && !!this.fbo;
    gl.bindFramebuffer(gl.FRAMEBUFFER, useHdr ? this.fbo : null);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.DEPTH_TEST);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.posTex);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.stateTex);
    const view = [p.view.xmin, p.view.xmax, p.view.ymin, p.view.ymax] as const;
    const fallbackScale = useHdr ? 1 : 0.55;

    // trails first, under the dots
    if (this.T > 1) {
      const tp = this.trail;
      gl.useProgram(tp.p);
      gl.uniform1i(tp.u.uPos, 0);
      gl.uniform1i(tp.u.uState, 1);
      gl.uniform1i(tp.u.uK, this.K);
      gl.uniform1i(tp.u.uW, this.W);
      gl.uniform4f(tp.u.uView, view[0], view[1], view[2], view[3]);
      gl.uniform2f(tp.u.uRes, w, h);
      gl.uniform1f(tp.u.uHead, p.head);
      for (const ts of this.trails.values()) {
        if (!ts.count) continue;
        gl.uniform1f(tp.u.uWidth, ts.width * this.dpr);
        gl.uniform1f(tp.u.uTau, ts.tau);
        gl.uniform1f(tp.u.uGain, ts.gain * fallbackScale);
        gl.uniform1f(tp.u.uFuture, ts.future);
        gl.uniform3f(tp.u.uTint, ts.tint ? ts.tint[0] : 1, ts.tint ? ts.tint[1] : 1, ts.tint ? ts.tint[2] : 1);
        gl.uniform1f(tp.u.uUseTint, ts.tint ? 1 : 0);
        gl.bindVertexArray(ts.vao);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, ts.count);
      }
      gl.bindVertexArray(null);
    }

    const pp = this.pts;
    gl.useProgram(pp.p);
    gl.bindVertexArray(this.vaoEmpty);
    gl.uniform1i(pp.u.uPos, 0);
    gl.uniform1i(pp.u.uState, 1);
    gl.uniform1i(pp.u.uK, this.K);
    gl.uniform1i(pp.u.uW, this.W);
    gl.uniform1i(pp.u.uI0, p.i0);
    gl.uniform1i(pp.u.uI1, p.i1);
    gl.uniform1f(pp.u.uE, p.e);
    gl.uniform4f(pp.u.uView, view[0], view[1], view[2], view[3]);
    gl.uniform1f(pp.u.uSize, p.pointPx * this.dpr);
    gl.uniform1f(pp.u.uSel, p.selActive ? 1 : 0);
    gl.uniform1f(pp.u.uDim, p.dimOthers);
    gl.uniform1i(pp.u.uHover, p.hoverK);
    gl.uniform1f(pp.u.uGain, p.gain * fallbackScale);
    gl.drawArrays(gl.POINTS, 0, this.K);
    gl.bindVertexArray(null);

    if (useHdr) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, w, h);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.disable(gl.BLEND);
      const cp = this.comp;
      gl.useProgram(cp.p);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.fboTex);
      gl.uniform1i(cp.u.uHdr, 0);
      gl.uniform1f(cp.u.uExposure, p.exposure);
      gl.uniform2f(cp.u.uTexel, 1 / w, 1 / h);
      gl.uniform1f(cp.u.uBloom, 0.55);
      gl.bindVertexArray(this.vaoEmpty);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.bindVertexArray(null);
    }
  }

  destroy() {
    const gl = this.gl;
    if (this.posTex) gl.deleteTexture(this.posTex);
    if (this.stateTex) gl.deleteTexture(this.stateTex);
    if (this.fbo) gl.deleteFramebuffer(this.fbo);
    if (this.fboTex) gl.deleteTexture(this.fboTex);
    for (const ts of this.trails.values()) {
      gl.deleteVertexArray(ts.vao);
      gl.deleteBuffer(ts.bufK);
      gl.deleteBuffer(ts.bufS);
    }
    this.trails.clear();
    this.posTex = null;
    this.stateTex = null;
    this.fbo = null;
    this.fboTex = null;
    this.fbw = 0;
    this.fbh = 0;
  }

  get size() {
    return { w: this.cssW, h: this.cssH, dpr: this.dpr };
  }
}
