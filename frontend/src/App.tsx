import { lazy } from 'react'
import { Route, Routes } from 'react-router'
import { RequireAuth, RequireOrgRole, RequireRole } from './auth/guards'
import { AppLayout } from './components/AppLayout'
import { AuditTab } from './kh/case/AuditTab'
import { CaseLayout } from './kh/case/CaseLayout'
import { ChatTab } from './kh/case/ChatTab'
import { FilesTab } from './kh/case/FilesTab'
import { HistoryTab } from './kh/case/HistoryTab'
import { OverviewTab } from './kh/case/OverviewTab'
import { ReportTab } from './kh/case/ReportTab'
import { TeamTab } from './kh/case/TeamTab'
import { CasesPage } from './kh/pages/CasesPage'
import { DashboardPage } from './kh/pages/DashboardPage'
import { EvidencePage } from './kh/pages/EvidencePage'
import { ContributionsPage, NotificationsPage } from './kh/pages/InboxPages'
import { RegisterCasePage } from './kh/pages/RegisterCasePage'
import { AuditPage } from './pages/AuditPage'
import { CaseDetailsPage } from './pages/CaseDetailsPage'
import { CreateAccountPage } from './pages/CreateAccountPage'
import { LoginPage } from './pages/LoginPage'
import { NewCasePage } from './pages/NewCasePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { SearchPage } from './pages/SearchPage'
import { SimilarToCasePage, UploadResultsPage } from './pages/SimilarPages'

// Loaded when first opened: the charts and graph drawing are large and only these screens use them.
const admin = () => import('./kh/pages/AdminPages')
const AdminOverviewPage = lazy(() => admin().then((m) => ({ default: m.AdminOverviewPage })))
const AdminCasesPage = lazy(() => admin().then((m) => ({ default: m.AdminCasesPage })))
const AdminCasePage = lazy(() => admin().then((m) => ({ default: m.AdminCasePage })))
const AdminEvidencePage = lazy(() => admin().then((m) => ({ default: m.AdminEvidencePage })))
const AdminActivityPage = lazy(() => admin().then((m) => ({ default: m.AdminActivityPage })))
const LinksTab = lazy(() => import('./kh/case/LinksTab').then((m) => ({ default: m.LinksTab })))
const IntelligenceTab = lazy(() => import('./kh/case/intelligence/IntelligenceTab').then((m) => ({ default: m.IntelligenceTab })))
const ImportsTab = lazy(() => import('./kh/case/imports/ImportsTab').then((m) => ({ default: m.ImportsTab })))
const CdrTab = lazy(() => import('./kh/case/CdrTab').then((m) => ({ default: m.CdrTab })))
const AdminIntegrationsPage = lazy(() => import('./kh/pages/AdminIntegrationsPage').then((m) => ({ default: m.AdminIntegrationsPage })))
const VerifyReportPage = lazy(() => import('./kh/pages/VerifyReportPage').then((m) => ({ default: m.VerifyReportPage })))
const PeoplePage = lazy(() => import('./kh/pages/PeoplePage').then((m) => ({ default: m.PeoplePage })))
const performance = () => import('./kh/pages/PerformancePage')
const PerformancePage = lazy(() => performance().then((m) => ({ default: m.PerformancePage })))
const StationPerformancePage = lazy(() => performance().then((m) => ({ default: m.StationPerformancePage })))
const OfficerPerformancePage = lazy(() => performance().then((m) => ({ default: m.OfficerPerformancePage })))
const MyProfilePage = lazy(() => import('./kh/pages/MyProfilePage').then((m) => ({ default: m.MyProfilePage })))
const AccountPage = lazy(() => import('./kh/pages/AccountPage').then((m) => ({ default: m.AccountPage })))

const CASE_CREATORS = ['super_admin', 'administrator', 'supervisor', 'investigator']
const ADMIN = ['super_admin']
const STATION_VIEWERS = ['super_admin', 'administrator', 'supervisor']

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/create-account" element={<CreateAccountPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        {/* Case Intelligence: similar-case search (Steps 0-14) */}
        <Route index element={<SearchPage />} />
        <Route path="cases/:displayId" element={<CaseDetailsPage />} />
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

        {/* Knight Hawk Case Management (Step 15) */}
        <Route path="kh">
          <Route index element={<DashboardPage />} />
          <Route path="cases" element={<CasesPage />} />
          <Route
            path="cases/new"
            element={
              <RequireOrgRole roles={CASE_CREATORS}>
                <RegisterCasePage />
              </RequireOrgRole>
            }
          />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="contributions" element={<ContributionsPage />} />
          <Route path="verify-report" element={<VerifyReportPage />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="profile" element={<MyProfilePage />} />
          <Route
            path="people"
            element={
              <RequireOrgRole roles={CASE_CREATORS}>
                <PeoplePage />
              </RequireOrgRole>
            }
          />
          <Route
            path="performance"
            element={
              <RequireOrgRole roles={CASE_CREATORS}>
                <PerformancePage />
              </RequireOrgRole>
            }
          />
          <Route
            path="performance/stations/:stationId"
            element={
              <RequireOrgRole roles={STATION_VIEWERS}>
                <StationPerformancePage />
              </RequireOrgRole>
            }
          />
          <Route
            path="performance/officers/:userId"
            element={
              <RequireOrgRole roles={CASE_CREATORS}>
                <OfficerPerformancePage />
              </RequireOrgRole>
            }
          />
          <Route path="evidence/:evidenceId" element={<EvidencePage />} />
          <Route path="case/:caseId" element={<CaseLayout />}>
            <Route index element={<OverviewTab />} />
            <Route path="files" element={<FilesTab />} />
            <Route path="chat" element={<ChatTab />} />
            <Route path="team" element={<TeamTab />} />
            <Route path="history" element={<HistoryTab />} />
            <Route path="links" element={<LinksTab />} />
            <Route path="reports" element={<ReportTab />} />
            <Route path="insights" element={<IntelligenceTab />} />
            <Route path="imports" element={<ImportsTab />} />
            <Route path="cdr" element={<CdrTab />} />
            <Route
              path="audit"
              element={
                <RequireOrgRole roles={ADMIN}>
                  <AuditTab />
                </RequireOrgRole>
              }
            />
          </Route>
          <Route
            path="admin"
            element={
              <RequireOrgRole roles={ADMIN}>
                <AdminOverviewPage />
              </RequireOrgRole>
            }
          />
          <Route
            path="admin/cases"
            element={
              <RequireOrgRole roles={ADMIN}>
                <AdminCasesPage />
              </RequireOrgRole>
            }
          />
          <Route
            path="admin/cases/:caseId"
            element={
              <RequireOrgRole roles={ADMIN}>
                <AdminCasePage />
              </RequireOrgRole>
            }
          />
          <Route
            path="admin/evidence"
            element={
              <RequireOrgRole roles={ADMIN}>
                <AdminEvidencePage />
              </RequireOrgRole>
            }
          />
          <Route
            path="admin/integrations"
            element={
              <RequireOrgRole roles={ADMIN}>
                <AdminIntegrationsPage />
              </RequireOrgRole>
            }
          />
          <Route
            path="admin/activity"
            element={
              <RequireOrgRole roles={ADMIN}>
                <AdminActivityPage />
              </RequireOrgRole>
            }
          />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
