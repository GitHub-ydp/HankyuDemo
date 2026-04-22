import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import EmailAnalysis from '../components/EmailAnalysis';
import EmailConnection from '../components/EmailConnection';
import EmailResults from '../components/EmailResults';
import EmailSearchInput from '../components/EmailSearchInput';
import { emailApi } from '../services/emailApi';
import type { EmailItem } from '../types/email';

export default function EmailSearch() {
  const { t } = useTranslation();
  const [indexCount, setIndexCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'search' | 'analyze' | null>(null);
  const [searchResults, setSearchResults] = useState<EmailItem[]>([]);
  const [analyzeResult, setAnalyzeResult] = useState<{ analysis: string; emails: EmailItem[] } | null>(null);
  const [currentQuery, setCurrentQuery] = useState('');

  const handleIndexComplete = (payload: { count: number; emails: EmailItem[] }) => {
    setIndexCount(payload.count);
    setMode('search');
    setCurrentQuery('');
    setAnalyzeResult(null);
    setSearchResults(payload.emails);
  };

  const handleSearch = async (query: string) => {
    setLoading(true);
    setMode('search');
    setCurrentQuery(query);
    setAnalyzeResult(null);
    try {
      const response = await emailApi.search(query);
      setSearchResults(response.results);
      message.success(t('email.searchSuccess', { count: response.count }));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('email.searchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyze = async (query: string) => {
    setLoading(true);
    setMode('analyze');
    setCurrentQuery(query);
    setSearchResults([]);
    try {
      const response = await emailApi.analyze(query);
      setAnalyzeResult({ analysis: response.analysis, emails: response.emails });
      message.success(t('email.analyzeSuccess'));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('email.analyzeFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('email.title')}</h1>
        <div className="sub">EMAIL ANALYSIS</div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ fontSize: 13, color: 'var(--ink-700)', lineHeight: 1.65 }}>
          {t('email.description')}
        </div>
      </div>

      <EmailConnection onIndexComplete={handleIndexComplete} />

      <EmailSearchInput
        onSearch={handleSearch}
        onAnalyze={handleAnalyze}
        loading={loading}
        disabled={indexCount === null || indexCount === 0}
      />

      {mode === 'search' && <EmailResults results={searchResults} loading={loading} />}

      {mode === 'analyze' && analyzeResult && (
        <EmailAnalysis
          analysis={analyzeResult.analysis}
          emails={analyzeResult.emails}
          loading={loading}
          query={currentQuery}
        />
      )}
    </div>
  );
}
