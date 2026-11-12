(function () {
  const inp = document.getElementById("tool-in");
  const out = document.getElementById("tool-out");
  const enc = new TextEncoder(), dec = new TextDecoder();

  const b64ToBytes = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/").replace(/\s/g, "") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0));
  const bytesToB64 = (b) => btoa(String.fromCharCode(...b));
  const hex = (buf) => [...new Uint8Array(buf)].map(x => x.toString(16).padStart(2, "0")).join("");

  async function digest(alg, s) { return hex(await crypto.subtle.digest(alg, enc.encode(s))); }

  function guessHash(s) {
    s = s.trim();
    if (/^\$2[aby]\$/.test(s)) return "bcrypt";
    if (/^\$6\$/.test(s)) return "SHA-512 crypt (Linux /etc/shadow)";
    if (/^\$5\$/.test(s)) return "SHA-256 crypt";
    if (/^\$1\$/.test(s)) return "MD5 crypt";
    if (/^\$argon2/.test(s)) return "Argon2";
    if (!/^[0-9a-f]+$/i.test(s)) return "Unbekannt (kein Hex-Format)";
    return ({ 32: "MD5 oder NTLM", 40: "SHA-1", 56: "SHA-224", 64: "SHA-256", 96: "SHA-384", 128: "SHA-512" })[s.length] || "Unbekannte Länge: " + s.length;
  }

  const tools = {
    b64enc: s => bytesToB64(enc.encode(s)),
    b64dec: s => dec.decode(b64ToBytes(s.trim())),
    hexenc: s => hex(enc.encode(s)),
    hexdec: s => dec.decode(Uint8Array.from((s.replace(/[^0-9a-f]/gi, "").match(/../g) || []).map(h => parseInt(h, 16)))),
    urlenc: s => encodeURIComponent(s),
    urldec: s => decodeURIComponent(s),
    rot13: s => s.replace(/[a-z]/gi, c => String.fromCharCode((c <= "Z" ? 90 : 122) >= (c = c.charCodeAt(0) + 13) ? c : c - 26)),
    binenc: s => [...enc.encode(s)].map(b => b.toString(2).padStart(8, "0")).join(" "),
    bindec: s => dec.decode(Uint8Array.from((s.replace(/[^01]/g, "").match(/.{8}/g) || []).map(b => parseInt(b, 2)))),
    jwt: s => {
      const parts = s.trim().split(".");
      if (parts.length < 2) throw new Error("Kein JWT (erwartet: header.payload.signatur)");
      const j = p => JSON.stringify(JSON.parse(dec.decode(b64ToBytes(p))), null, 2);
      return "// Header\n" + j(parts[0]) + "\n\n// Payload\n" + j(parts[1]) + "\n\n// Signatur wird NICHT geprüft";
    },
    sha1: s => digest("SHA-1", s),
    sha256: s => digest("SHA-256", s),
    hashid: s => guessHash(s),
  };

  document.querySelectorAll("[data-tool]").forEach(btn => btn.addEventListener("click", async () => {
    try { out.value = await tools[btn.dataset.tool](inp.value); }
    catch (err) { out.value = "Fehler: " + err.message; }
  }));
  document.getElementById("tool-swap").addEventListener("click", () => { inp.value = out.value; out.value = ""; });
})();
