import { useState } from 'react';
import { Navbar, type NavTab } from './components/Navbar';
import { LoginGate } from './components/LoginGate';
import { StaffView } from './views/StaffView';
import { AbsencesView } from './views/AbsencesView';
import { PreAssignedView } from './views/PreAssignedView';
import { MatrixView } from './views/MatrixView';
import { FairnessView } from './views/FairnessView';
import { AboutView } from './views/AboutView';

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('staff');
  const [currentQuarter, setCurrentQuarter] = useState('2026-Q4');

  const handleLogout = () => {
    localStorage.removeItem('clinic_auth_token');
    window.location.reload();
  };

  const renderActiveView = () => {
    switch (activeTab) {
      case 'staff':
        return <StaffView />;
      case 'absences':
        return <AbsencesView />;
      case 'preassignments':
        return <PreAssignedView />;
      case 'matrix':
        return (
          <MatrixView
            currentQuarter={currentQuarter}
            onQuarterChange={setCurrentQuarter}
          />
        );
      case 'fairness':
        return (
          <FairnessView
            currentQuarter={currentQuarter}
            onQuarterChange={setCurrentQuarter}
          />
        );
      case 'about':
        return <AboutView />;
      default:
        return <StaffView />;
    }
  };

  return (
    <LoginGate>
      <div className="min-h-screen bg-[#fcfbf9] text-stone-800 flex flex-col font-sans">
        {/* Top Single-Line Ribbon */}
        <Navbar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          currentQuarter={currentQuarter}
          onQuarterChange={setCurrentQuarter}
        />

        {/* Main Content Area */}
        <main className="flex-1 mx-auto max-w-7xl w-full px-4 sm:px-6 lg:px-8 py-7">
          {renderActiveView()}
        </main>

        {/* Warm Clinic Footer with Logout */}
        <footer className="border-t border-stone-200/80 bg-white/60 py-3.5 px-4 flex items-center justify-between text-xs text-stone-400">
          <span>Tierklinik Dr. Trillig Obertshausen &middot; Personal- & Dienstplanungsportal</span>
          <button
            onClick={handleLogout}
            className="text-stone-400 hover:text-stone-700 underline cursor-pointer"
          >
            Abmelden
          </button>
        </footer>
      </div>
    </LoginGate>
  );
}

export default App;
