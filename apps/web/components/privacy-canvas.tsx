"use client";
import { Button } from "./ui";
import {
  Brush,
  Crop,
  ImagePlus,
  Redo2,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  Square,
} from "lucide-react";
import { PointerEvent, useEffect, useRef, useState } from "react";

type Snapshot = { url: string; width: number; height: number };
export function PrivacyCanvas({
  onSubmit,
  loading,
}: {
  onSubmit: (blob: Blob, name: string) => Promise<boolean>;
  loading: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const drawing = useRef(false);
  const start = useRef({ x: 0, y: 0 });
  const [fileName, setFileName] = useState("");
  const [tool, setTool] = useState<"rect" | "brush" | "crop">("rect");
  const [ready, setReady] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [fileError, setFileError] = useState("");
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [index, setIndex] = useState(-1);
  useEffect(() => {
    if (!ready || !history[0] || !canvasRef.current) return;
    restore(history[0]);
    // The first snapshot is drawn once the canvas has actually mounted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);
  function coords(e: PointerEvent<HTMLCanvasElement>) {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return {
      x: ((e.clientX - r.left) * c.width) / r.width,
      y: ((e.clientY - r.top) * c.height) / r.height,
    };
  }
  function snapshot() {
    const c = canvasRef.current!;
    const item = {
      url: c.toDataURL("image/png"),
      width: c.width,
      height: c.height,
    };
    setHistory((old) => {
      const next = old.slice(0, index + 1);
      next.push(item);
      return next.slice(-20);
    });
    setIndex((old) => Math.min(old + 1, 19));
  }
  function restore(item: Snapshot) {
    const c = canvasRef.current!;
    const ctx = c.getContext("2d")!;
    const img = new Image();
    img.onload = () => {
      c.width = item.width;
      c.height = item.height;
      ctx.drawImage(img, 0, 0);
    };
    img.src = item.url;
  }
  function undo() {
    if (index <= 0) return;
    const next = index - 1;
    setIndex(next);
    restore(history[next]);
  }
  function redo() {
    if (index >= history.length - 1) return;
    const next = index + 1;
    setIndex(next);
    restore(history[next]);
  }
  function loadFile(file?: File) {
    if (!file || !file.type.startsWith("image/")) {
      setFileError("请选择 PNG、JPG、WebP 等图片文件。");
      return;
    }
    setFileName(file.name);
    setConfirmed(false);
    setCompleted(false);
    setFileError("");
    setReady(false);
    setHistory([]);
    setIndex(-1);
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      const c = document.createElement("canvas");
      const max = 2400;
      const scale = Math.min(1, max / Math.max(image.width, image.height));
      c.width = Math.round(image.width * scale);
      c.height = Math.round(image.height * scale);
      c.getContext("2d")!.drawImage(image, 0, 0, c.width, c.height);
      const first = {
        url: c.toDataURL("image/png"),
        width: c.width,
        height: c.height,
      };
      setHistory([first]);
      setIndex(0);
      setReady(true);
      URL.revokeObjectURL(url);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      setFileError("这张图片无法打开，请换一张有效图片再试。");
    };
    image.src = url;
  }
  function resetForNextImage() {
    setFileName("");
    setConfirmed(false);
    setHistory([]);
    setIndex(-1);
    setReady(false);
    setCompleted(true);
    if (fileRef.current) fileRef.current.value = "";
  }
  function pointerDown(e: PointerEvent<HTMLCanvasElement>) {
    if (!ready) return;
    drawing.current = true;
    start.current = coords(e);
    e.currentTarget.setPointerCapture(e.pointerId);
    if (tool === "brush") {
      const ctx = e.currentTarget.getContext("2d")!;
      ctx.beginPath();
      ctx.moveTo(start.current.x, start.current.y);
      ctx.strokeStyle = "#170b20";
      ctx.lineWidth = Math.max(18, e.currentTarget.width * 0.025);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
    }
  }
  function pointerMove(e: PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current || tool !== "brush") return;
    const p = coords(e);
    const ctx = e.currentTarget.getContext("2d")!;
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  }
  function pointerUp(e: PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    drawing.current = false;
    const end = coords(e);
    const c = e.currentTarget;
    const ctx = c.getContext("2d")!;
    const x = Math.max(0, Math.min(start.current.x, end.x));
    const y = Math.max(0, Math.min(start.current.y, end.y));
    const w = Math.min(c.width - x, Math.abs(end.x - start.current.x));
    const h = Math.min(c.height - y, Math.abs(end.y - start.current.y));
    if (tool === "rect" && w > 3 && h > 3) {
      ctx.fillStyle = "#170b20";
      ctx.fillRect(x, y, w, h);
    } else if (tool === "crop" && w > 20 && h > 20) {
      const data = ctx.getImageData(x, y, w, h);
      c.width = Math.round(w);
      c.height = Math.round(h);
      ctx.putImageData(data, 0, 0);
    }
    snapshot();
  }
  async function submit() {
    const c = canvasRef.current;
    if (!c || !confirmed) return;
    const blob = await new Promise<Blob | null>((resolve) =>
      c.toBlob(resolve, "image/jpeg", 0.92),
    );
    if (blob) {
      const accepted = await onSubmit(
        blob,
        `masked-${fileName.replace(/\.[^.]+$/, "") || "asset"}.jpg`,
      );
      if (accepted) resetForNextImage();
    }
  }
  return (
    <div className="privacy-editor">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          loadFile(file);
        }}
      />
      {!ready ? (
        <>
          <button
            className="privacy-drop"
            onClick={() => fileRef.current?.click()}
          >
            <div>
              <ImagePlus />
              <strong>{completed ? "继续识别下一张资产截图" : "选一张资产截图"}</strong>
              <span>{completed ? "上一张已处理完成，可以直接接着上传。" : "选好以后，可以先把不想露出的信息遮住。"}</span>
            </div>
          </button>
          {fileError ? <div className="inline-error">{fileError}</div> : null}
        </>
      ) : (
        <>
          <div className="editor-toolbar">
            <div className="tool-group">
              <button
                className={tool === "rect" ? "active" : ""}
                onClick={() => setTool("rect")}
              >
                <Square />
                矩形遮挡
              </button>
              <button
                className={tool === "brush" ? "active" : ""}
                onClick={() => setTool("brush")}
              >
                <Brush />
                自由涂抹
              </button>
              <button
                className={tool === "crop" ? "active" : ""}
                onClick={() => setTool("crop")}
              >
                <Crop />
                裁剪
              </button>
            </div>
            <div className="tool-group">
              <button disabled={index <= 0} onClick={undo}>
                <RotateCcw />
                撤销
              </button>
              <button disabled={index >= history.length - 1} onClick={redo}>
                <Redo2 />
                重做
              </button>
              <button onClick={() => fileRef.current?.click()}>
                <ImagePlus />
                换图
              </button>
            </div>
          </div>
          <div className="canvas-stage">
            <canvas
              ref={canvasRef}
              onPointerDown={pointerDown}
              onPointerMove={pointerMove}
              onPointerUp={pointerUp}
              onPointerCancel={pointerUp}
            />
            <span className="local-only">
              <ShieldCheck />
              正在编辑
            </span>
          </div>
          <div className="privacy-check">
            <label>
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              <span>
                <strong>已经检查好了，可以开始识别</strong>
                <small>
                  再看一眼姓名、完整账号、手机号、证件号和二维码有没有遮住。
                </small>
              </span>
            </label>
            <Button loading={loading} disabled={!confirmed} onClick={submit}>
              <ScanLine />
              {loading ? "正在识别，请稍等…" : "交给怀特识别"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
