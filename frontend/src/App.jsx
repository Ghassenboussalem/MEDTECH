import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import NotebookList from './pages/NotebookList';
import NotebookDetail from './pages/NotebookDetail';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<NotebookList />} />
        <Route path="/notebooks/:id" element={<NotebookDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
