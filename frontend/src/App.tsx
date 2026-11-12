import { Route, Routes } from 'react-router'
import { RequireAuth, RequireRole } from './auth/guards'
import { AppLayout } from './components/AppLayout'
import { AuditPage } from './pages/AuditPage'
import { CaseDetailsPage } from './pages/CaseDetailsPage'
import { CdrAnalysisPage } from './pages/CdrAnalysisPage'
import { LoginPage } from './pages/LoginPage'
import { NewCasePage } from './pages/NewCasePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { SearchPage } from './pages/SearchPage'
import { SimilarToCasePage, UploadResultsPage } from './pages/SimilarPages'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<SearchPage />} />
        <Route path="cases/:displayId" element={<CaseDetailsPage />} />
        <Route path="cases/:displayId/cdr" element={<CdrAnalysisPage />} />
        <Route path="cases/:displayId/similar" element={<SimilarToCasePage />} />
        <Route
          path="new"
          element={
            <RequireRole roles={['analyst', 'admin']}>
              <NewCasePage />
            </RequireRole>
          }
        />
        <Route
          path="uploads/:uploadId"
          element={
            <RequireRole roles={['analyst', 'admin']}>
              <UploadResultsPage />
            </RequireRole>
          }
        />
        <Route
          path="audit"
          element={
            <RequireRole roles={['admin']}>
              <AuditPage />
            </RequireRole>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
