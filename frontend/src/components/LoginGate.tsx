import React, { useState, useEffect } from 'react';
import { Lock, ArrowRight, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { Button } from './ui/Button';
import { checkAuthStatus, getAuthToken, loginClinic } from '../lib/api';

interface LoginGateProps {
  children: React.ReactNode;
}

export const LoginGate: React.FC<LoginGateProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function evaluateAuth() {
      try {
        const status = await checkAuthStatus();
        if (!status.required) {
          if (mounted) setIsAuthenticated(true);
          return;
        }
      } catch {
        // offline or local dev fallback
      }

      const token = getAuthToken();
      if (mounted) {
        setIsAuthenticated(!!token);
      }
    }

    evaluateAuth();

    const handleUnauthorized = () => {
      if (mounted) setIsAuthenticated(false);
    };

    window.addEventListener('clinic:unauthorized', handleUnauthorized);
    return () => {
      mounted = false;
      window.removeEventListener('clinic:unauthorized', handleUnauthorized);
    };
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setLoading(true);

    try {
      await loginClinic(password);
      setIsAuthenticated(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Anmeldung fehlgeschlagen';
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen bg-[#fcfbf9] flex items-center justify-center">
        <div className="text-xs text-stone-400">Lade Portal...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#fcfbf9] flex flex-col items-center justify-center p-4">
        <div className="w-full max-w-sm bg-white rounded-2xl border border-stone-200/90 shadow-md p-7 space-y-6">
          {/* Logo & Heading */}
          <div className="text-center space-y-3">
            <img
              src="/logo-trillig.png"
              alt="Tierklinik Dr. Trillig"
              className="h-10 mx-auto object-contain"
            />
            <div>
              <h1 className="text-lg font-bold text-stone-900 tracking-tight">
                Dienstplanungsportal
              </h1>
              <p className="text-xs text-stone-500 mt-0.5">
                Bitte geben Sie das Klinik-Passwort ein, um fortzufahren.
              </p>
            </div>
          </div>

          {/* Error Message */}
          {errorMsg && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Passwort
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="Klinik-Passwort"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-3 pr-10 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b] transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-stone-400 hover:text-stone-600 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading || !password}
              variant="primary"
              className="w-full py-2.5 text-xs font-semibold shadow-xs"
            >
              {loading ? (
                'Anmeldung läuft...'
              ) : (
                <span className="flex items-center justify-center gap-1.5">
                  <Lock className="h-3.5 w-3.5" />
                  <span>Anmelden</span>
                  <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </span>
              )}
            </Button>
          </form>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};

