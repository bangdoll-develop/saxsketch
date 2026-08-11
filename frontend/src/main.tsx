import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { PathPickerProvider } from "./pathPicker";
import "./styles.css";

// パス選択は App より外側に置く。App 自身も usePathPicker を使うので、
// 同じコンポーネントで Provider を張ると自分の Context を読めない。
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PathPickerProvider>
      <App />
    </PathPickerProvider>
  </StrictMode>,
);
