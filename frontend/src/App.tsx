import { Route, Routes } from "react-router-dom";
import { BatchPage } from "./Batch";
import { BatchesPage } from "./Batches";
import { ComparePage } from "./Compare";
import { ImportPage } from "./Import";
import { RulesPage } from "./Rules";
import { Shell } from "./Shell";

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<ImportPage />} />
        <Route path="/batches" element={<BatchesPage />} />
        <Route path="/batches/:batchId" element={<BatchPage />} />
        <Route path="/batches/:batchId/compare/:otherId" element={<ComparePage />} />
        <Route path="/rules" element={<RulesPage />} />
        <Route path="*" element={<div className="empty">页面不存在</div>} />
      </Routes>
    </Shell>
  );
}
