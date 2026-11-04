import { useState } from 'react';
import { Navbar, type NavTab } from './components/Navbar';
import { StaffView } from './views/StaffView';
import { AbsencesView } from './views/AbsencesView';
import { MatrixView } from './views/MatrixView';
import { FairnessView } from './views/FairnessView';
import { AboutView } from './views/AboutView';

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('staff');
  const [currentQuarter, setCurrentQuarter] = useState('2026-Q2');

  const renderActiveView = () => {
    switch (activeTab) {
      case 'staff':
        return <StaffView />;
      case 'absences':
        return <AbsencesView />;
      case 'matrix':
        return <MatrixView />;
      case 'fairness':
        return <FairnessView />;
      case 'about':
        return <AboutView />;
      default:
        return <StaffView />;
    }
  };

  return (
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

      {/* Warm Clinic Footer */}
      <footer className="border-t border-stone-200/80 bg-white/60 py-4 text-center text-xs text-stone-400">
        Tierklinik Dr. Trillig Obertshausen &middot; Personal- & Dienstplanungsportal &middot; Intern
      </footer>
    </div>
  );
}

export default App;
