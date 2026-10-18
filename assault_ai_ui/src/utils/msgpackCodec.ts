/**
 * Zero-dependency RFC-8949 MessagePack Binary Decoder & Encoder for Assault UI & MLOps Viewer
 * Implements Roadmap Section 6.5: Binary WebSocket & Telemetry Streaming (<5ms decode latency).
 */

const textDecoder = new TextDecoder("utf-8");
const textEncoder = new TextEncoder();

export function decodeMsgpack(input: ArrayBuffer | Uint8Array): any {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;

  function read(): any {
    const b = bytes[offset++];
    if (b <= 0x7f) return b;
    if (b >= 0xe0) return b - 256;

    // fixmap
    if (b >= 0x80 && b <= 0x8f) {
      const n = b & 0x0f;
      const obj: Record<string, any> = {};
      for (let i = 0; i < n; i++) {
        const k = String(read());
        obj[k] = read();
      }
      return obj;
    }

    // fixarray
    if (b >= 0x90 && b <= 0x9f) {
      const n = b & 0x0f;
      const arr = new Array(n);
      for (let i = 0; i < n; i++) arr[i] = read();
      return arr;
    }

    // fixstr
    if (b >= 0xa0 && b <= 0xbf) {
      const n = b & 0x1f;
      const s = textDecoder.decode(bytes.subarray(offset, offset + n));
      offset += n;
      return s;
    }

    switch (b) {
      case 0xc0:
        return null;
      case 0xc2:
        return false;
      case 0xc3:
        return true;
      case 0xc4: {
        const n = bytes[offset++];
        const slice = bytes.subarray(offset, offset + n);
        offset += n;
        return slice;
      }
      case 0xc5: {
        const n = view.getUint16(offset, false);
        offset += 2;
        const slice = bytes.subarray(offset, offset + n);
        offset += n;
        return slice;
      }
      case 0xc6: {
        const n = view.getUint32(offset, false);
        offset += 4;
        const slice = bytes.subarray(offset, offset + n);
        offset += n;
        return slice;
      }
      case 0xca: {
        const v = view.getFloat32(offset, false);
        offset += 4;
        return v;
      }
      case 0xcb: {
        const v = view.getFloat64(offset, false);
        offset += 8;
        return v;
      }
      case 0xcc:
        return bytes[offset++];
      case 0xcd: {
        const v = view.getUint16(offset, false);
        offset += 2;
        return v;
      }
      case 0xce: {
        const v = view.getUint32(offset, false);
        offset += 4;
        return v;
      }
      case 0xcf: {
        const hi = view.getUint32(offset, false);
        const lo = view.getUint32(offset + 4, false);
        offset += 8;
        return hi * 4294967296 + lo;
      }
      case 0xd0: {
        const v = view.getInt8(offset);
        offset += 1;
        return v;
      }
      case 0xd1: {
        const v = view.getInt16(offset, false);
        offset += 2;
        return v;
      }
      case 0xd2: {
        const v = view.getInt32(offset, false);
        offset += 4;
        return v;
      }
      case 0xd3: {
        const hi = view.getInt32(offset, false);
        const lo = view.getUint32(offset + 4, false);
        offset += 8;
        return hi * 4294967296 + lo;
      }
      case 0xd9: {
        const n = bytes[offset++];
        const s = textDecoder.decode(bytes.subarray(offset, offset + n));
        offset += n;
        return s;
      }
      case 0xda: {
        const n = view.getUint16(offset, false);
        offset += 2;
        const s = textDecoder.decode(bytes.subarray(offset, offset + n));
        offset += n;
        return s;
      }
      case 0xdb: {
        const n = view.getUint32(offset, false);
        offset += 4;
        const s = textDecoder.decode(bytes.subarray(offset, offset + n));
        offset += n;
        return s;
      }
      case 0xdc: {
        const n = view.getUint16(offset, false);
        offset += 2;
        const arr = new Array(n);
        for (let i = 0; i < n; i++) arr[i] = read();
        return arr;
      }
      case 0xdd: {
        const n = view.getUint32(offset, false);
        offset += 4;
        const arr = new Array(n);
        for (let i = 0; i < n; i++) arr[i] = read();
        return arr;
      }
      case 0xde: {
        const n = view.getUint16(offset, false);
        offset += 2;
        const obj: Record<string, any> = {};
        for (let i = 0; i < n; i++) {
          const k = String(read());
          obj[k] = read();
        }
        return obj;
      }
      case 0xdf: {
        const n = view.getUint32(offset, false);
        offset += 4;
        const obj: Record<string, any> = {};
        for (let i = 0; i < n; i++) {
          const k = String(read());
          obj[k] = read();
        }
        return obj;
      }
      default:
        throw new Error(`Unsupported MessagePack byte: 0x${b.toString(16)}`);
    }
  }

  return read();
}

export function encodeMsgpack(value: any): Uint8Array {
  const chunks: number[] = [];

  function writeU16(v: number) {
    chunks.push((v >>> 8) & 0xff, v & 0xff);
  }
  function writeU32(v: number) {
    chunks.push((v >>> 24) & 0xff, (v >>> 16) & 0xff, (v >>> 8) & 0xff, v & 0xff);
  }

  function pack(v: any) {
    if (v === null || v === undefined) {
      chunks.push(0xc0);
      return;
    }
    if (typeof v === "boolean") {
      chunks.push(v ? 0xc3 : 0xc2);
      return;
    }
    if (typeof v === "number") {
      if (!Number.isFinite(v)) {
        chunks.push(0xc0);
        return;
      }
      if (Number.isInteger(v)) {
        if (v >= 0 && v <= 0x7f) {
          chunks.push(v);
        } else if (v >= -32 && v < 0) {
          chunks.push(v & 0xff);
        } else if (v >= 0 && v <= 0xff) {
          chunks.push(0xcc, v);
        } else if (v >= 0 && v <= 0xffff) {
          chunks.push(0xcd);
          writeU16(v);
        } else if (v >= 0 && v <= 0xffffffff) {
          chunks.push(0xce);
          writeU32(v);
        } else if (v >= -128 && v < 0) {
          chunks.push(0xd0, v & 0xff);
        } else if (v >= -32768 && v < 0) {
          chunks.push(0xd1);
          writeU16(v & 0xffff);
        } else if (v >= -2147483648 && v < 0) {
          chunks.push(0xd2);
          writeU32(v >>> 0);
        } else {
          const fbuf = new ArrayBuffer(8);
          new DataView(fbuf).setFloat64(0, v, false);
          chunks.push(0xcb, ...new Uint8Array(fbuf));
        }
      } else {
        const fbuf = new ArrayBuffer(8);
        new DataView(fbuf).setFloat64(0, v, false);
        chunks.push(0xcb, ...new Uint8Array(fbuf));
      }
      return;
    }
    if (typeof v === "string") {
      const bytes = textEncoder.encode(v);
      const n = bytes.length;
      if (n <= 31) {
        chunks.push(0xa0 | n);
      } else if (n <= 0xff) {
        chunks.push(0xd9, n);
      } else if (n <= 0xffff) {
        chunks.push(0xda);
        writeU16(n);
      } else {
        chunks.push(0xdb);
        writeU32(n);
      }
      for (let i = 0; i < n; i++) chunks.push(bytes[i]);
      return;
    }
    if (Array.isArray(v)) {
      const n = v.length;
      if (n <= 15) {
        chunks.push(0x90 | n);
      } else if (n <= 0xffff) {
        chunks.push(0xdc);
        writeU16(n);
      } else {
        chunks.push(0xdd);
        writeU32(n);
      }
      for (let i = 0; i < n; i++) pack(v[i]);
      return;
    }
    if (typeof v === "object") {
      const keys = Object.keys(v);
      const n = keys.length;
      if (n <= 15) {
        chunks.push(0x80 | n);
      } else if (n <= 0xffff) {
        chunks.push(0xde);
        writeU16(n);
      } else {
        chunks.push(0xdf);
        writeU32(n);
      }
      for (const k of keys) {
        pack(k);
        pack(v[k]);
      }
      return;
    }
    chunks.push(0xc0);
  }

  pack(value);
  return new Uint8Array(chunks);
}
