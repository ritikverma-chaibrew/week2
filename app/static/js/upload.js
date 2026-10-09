const MAX = 10;

/** Resize to <=1024px JPEG in the browser so uploads are small and fast. */
export async function compress(file, max = 1024) {
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k);
  c.height = Math.round(bmp.height * k);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("encode"))), "image/jpeg", 0.82));
}

/** Drop zone + thumbnails. Returns {blobs(), onChange}. */
export function mountDropzone(zone, input, thumbs, onChange) {
  const items = []; // {blob, url}
  const refresh = () => {
    thumbs.replaceChildren(
      ...items.map((it, i) => {
        const d = document.createElement("div");
        d.innerHTML = `<img alt="Your photo ${i + 1}" src="${it.url}"><button aria-label="Remove photo" type="button">×</button>`;
        d.querySelector("button").onclick = () => {
          URL.revokeObjectURL(it.url);
          items.splice(items.indexOf(it), 1);
          refresh();
        };
        return d;
      })
    );
    onChange(items.length);
  };
  async function add(files) {
    for (const f of [...files].filter((f) => f.type.startsWith("image/"))) {
      if (items.length >= MAX) break;
      try {
        const blob = await compress(f);
        items.push({ blob, url: URL.createObjectURL(blob) });
      } catch {
        /* unreadable file: skip */
      }
    }
    refresh();
  }
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.click()));
  input.addEventListener("change", () => { add(input.files); input.value = ""; });
  ["dragover", "dragenter"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, () => zone.classList.remove("over")));
  zone.addEventListener("drop", (e) => { e.preventDefault(); add(e.dataTransfer.files); });
  return { blobs: () => items.map((i) => i.blob) };
}
