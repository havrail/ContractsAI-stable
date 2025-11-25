import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FolderOpen, Play, Loader2, Trash2, Clock, Download, Sparkles, X, CheckSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ResultsTable from './ResultsTable';
import ReviewQueue from './ReviewQueue';

const API_URL = "http://localhost:8000";
const API_KEY = "dev-key-12345"; // Must match .env

// Configure axios defaults
axios.defaults.headers.common['X-API-Key'] = API_KEY;

export default function Dashboard() {
    const [activeTab, setActiveTab] = useState('analysis'); // 'analysis' or 'review'
    const [folderPath, setFolderPath] = useState("");
    const [status, setStatus] = useState("Hazır");
    const [progress, setProgress] = useState(0);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [results, setResults] = useState([]);
    const [jobId, setJobId] = useState(null);
    const [startTime, setStartTime] = useState(null);
    const [estimatedTime, setEstimatedTime] = useState(null);
    const [recentFolders, setRecentFolders] = useState([]);

    // Load recent folders from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem('recentFolders');
        if (saved) {
            setRecentFolders(JSON.parse(saved));
        }
    }, []);

    // Poll job status while analyzing
    useEffect(() => {
        let interval;
        if (isAnalyzing && jobId) {
            interval = setInterval(async () => {
                try {
                    const res = await axios.get(`${API_URL}/status/${jobId}`);
                    setStatus(res.data.message);
                    setProgress(res.data.progress);

                    // Update estimated time from backend
                    if (res.data.estimated_remaining !== undefined) {
                        setEstimatedTime(res.data.estimated_remaining);
                    }

                    if (res.data.status === "COMPLETED" || res.data.status === "FAILED") {
                        setIsAnalyzing(false);
                        setStartTime(null);
                        setEstimatedTime(null);
                        fetchResults();
                    }
                } catch (e) {
                    console.error(e);
                }
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [isAnalyzing, jobId]);

    // Track elapsed time locally for display
    const [elapsedTime, setElapsedTime] = useState(0);
    useEffect(() => {
        let timer;
        if (isAnalyzing && startTime) {
            timer = setInterval(() => {
                setElapsedTime((Date.now() - startTime) / 1000);
            }, 1000);
        } else {
            setElapsedTime(0);
        }
        return () => clearInterval(timer);
    }, [isAnalyzing, startTime]);

    const fetchResults = async () => {
        try {
            const res = await axios.get(`${API_URL}/results`);
            setResults(res.data);
        } catch (e) {
            console.error(e);
        }
    };

    // Load results initially and after analysis finishes
    useEffect(() => {
        if (!isAnalyzing) {
            fetchResults();
        }
    }, [isAnalyzing]);

    const handleFolderSelect = () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.webkitdirectory = true;
        input.directory = true;
        input.multiple = true;
        input.onchange = (e) => {
            const files = e.target.files;
            if (files.length > 0) {
                const firstFile = files[0];
                let selectedPath = '';
                if (firstFile.path) {
                    // Tauri/Electron: full directory path
                    const fullPath = firstFile.path.substring(0, firstFile.path.lastIndexOf('\\'));
                    selectedPath = fullPath;
                    setFolderPath(fullPath);
                } else {
                    // Web fallback: use folder name
                    const relativePath = firstFile.webkitRelativePath || '';
                    if (relativePath) {
                        const folderName = relativePath.split('/')[0];
                        selectedPath = folderName;
                        setFolderPath(folderName);
                    }
                }

                // Save to recent folders (max 5)
                if (selectedPath) {
                    const updated = [selectedPath, ...recentFolders.filter(f => f !== selectedPath)].slice(0, 5);
                    setRecentFolders(updated);
                    localStorage.setItem('recentFolders', JSON.stringify(updated));
                }
            }
        };
        input.click();
    };

    const handleStart = async () => {
        if (!folderPath) return;
        try {
            const res = await axios.post(`${API_URL}/analyze`, { folder_path: folderPath });
            setJobId(res.data.job_id);
            setIsAnalyzing(true);
            setStartTime(Date.now());
            setProgress(0);
        } catch (e) {
            const errorMsg = e.response?.data?.detail || e.message;
            alert("Hata: " + errorMsg);
        }
    };

    const handleClearCache = async () => {
        if (!confirm("Tüm sonuçları silmek istediğinizden emin misiniz?")) return;
        try {
            await axios.delete(`${API_URL}/results`);
            setResults([]);
            alert("Önbellek temizlendi!");
        } catch (e) {
            alert("Temizleme hatası: " + e.message);
        }
    };

    const formatTime = (seconds) => {
        if (!seconds || seconds === Infinity) return "Hesaplanıyor...";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };


    // Logları txt olarak indir
    const handleDownloadLogs = async () => {
        try {
            const res = await axios.get(`${API_URL}/logs/download`, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/plain' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = 'system_logs.txt';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            alert('Loglar indirilemedi: ' + e.message);
        }
    };

    return (
        <div className="min-h-screen p-8 relative z-10">
            <div className="max-w-7xl mx-auto space-y-8">
                {/* En üstte log indirme butonu */}
                <div className="flex justify-between items-center pt-2">
                    {/* Tab Navigation */}
                    <div className="flex gap-2 bg-slate-900/50 p-1 rounded-xl">
                        <button
                            onClick={() => setActiveTab('analysis')}
                            className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-all ${
                                activeTab === 'analysis'
                                    ? 'bg-violet-600 text-white'
                                    : 'text-gray-400 hover:text-white'
                            }`}
                        >
                            <Sparkles className="w-4 h-4" />
                            Analysis
                        </button>
                        <button
                            onClick={() => setActiveTab('review')}
                            className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-all ${
                                activeTab === 'review'
                                    ? 'bg-violet-600 text-white'
                                    : 'text-gray-400 hover:text-white'
                            }`}
                        >
                            <CheckSquare className="w-4 h-4" />
                            Review Queue
                        </button>
                    </div>

                    <button
                        onClick={handleDownloadLogs}
                        className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors bg-blue-500/10 px-3 py-1.5 rounded-lg border border-blue-500/20"
                    >
                        <Download className="w-3 h-3" /> Logları İndir (txt)
                    </button>
                </div>

                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="text-center space-y-4 relative">
                    <div className="inline-flex items-center gap-3 px-6 py-3 rounded-full glass">
                        <Sparkles className="w-5 h-5 text-violet-400" />
                        <span className="text-sm font-medium bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
                            AI-Powered Contract Analysis
                        </span>
                    </div>
                    <h1 className="text-6xl font-bold">
                        <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-pink-400 bg-clip-text text-transparent">
                            Contracts AI
                        </span>
                    </h1>
                    <p className="text-gray-400 text-lg">Sözleşmelerinizi saniyeler içinde analiz edin</p>
                </motion.div>

                {/* Tab Content */}
                {activeTab === 'analysis' ? (
                    <>
                        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 shadow-2xl">
                            <div className="space-y-6">
                                <div className="space-y-3">
                                    <label className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                                        <FolderOpen className="w-4 h-4 text-violet-400" /> Klasör Yolu
                                    </label>
                                    <div className="flex gap-3">
                                        <div className="relative group flex-1">
                                            <input
                                                type="text"
                                                value={folderPath}
                                                onChange={(e) => setFolderPath(e.target.value)}
                                                placeholder="C:\\Users\\Documents\\Contracts"
                                                className="w-full bg-slate-900/50 border-2 border-slate-700/50 rounded-2xl py-4 px-6 text-white placeholder-gray-500 focus:border-violet-500 focus:ring-4 focus:ring-violet-500/20 transition-all outline-none group-hover:border-slate-600/50"
                                            />
                                            <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                                        </div>
                                        <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={handleFolderSelect} className="h-14 px-6 rounded-2xl font-semibold flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white border-2 border-slate-700 transition-all">
                                            <FolderOpen className="w-5 h-5" /> Seç
                                        </motion.button>
                                    </div>
                                    {/* Warning for web environment */}
                                    <p className="text-xs text-yellow-300 mt-1">Web tarayıcısı yalnızca klasör adını alabilir; tam dosya yolu gerektiren analiz için masaüstü (Tauri) sürümünü kullanın.</p>

                            {/* Recent Folders Dropdown */}
                            {recentFolders.length > 0 && (
                                <div className="mt-2">
                                    <label className="text-xs text-gray-400 mb-1 block">Son Klasörler:</label>
                                    <div className="flex flex-wrap gap-2">
                                        {recentFolders.map((folder, idx) => (
                                            <motion.button
                                                key={idx}
                                                whileHover={{ scale: 1.05 }}
                                                whileTap={{ scale: 0.95 }}
                                                onClick={() => setFolderPath(folder)}
                                                className="px-3 py-1 text-xs rounded-lg bg-slate-800/50 hover:bg-slate-700/50 text-gray-300 border border-slate-700/50 hover:border-violet-500/30 transition-all"
                                            >
                                                📁 {folder.length > 40 ? '...' + folder.slice(-37) : folder}
                                            </motion.button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="flex gap-4">
                            <motion.button
                                whileHover={{ scale: 1.02 }}
                                whileTap={{ scale: 0.98 }}
                                onClick={handleStart}
                                disabled={isAnalyzing || !folderPath}
                                className={`flex-1 h-14 rounded-2xl font-bold flex items-center justify-center gap-3 transition-all ${isAnalyzing || !folderPath ? 'bg-slate-800 text-gray-500 cursor-not-allowed' : 'bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-600 text-white shadow-lg shadow-violet-500/30 hover:shadow-violet-500/50'}`}
                            >
                                {isAnalyzing ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        <span>İşleniyor...</span>
                                    </>
                                ) : (
                                    <>
                                        <Play className="w-5 h-5 fill-current" />
                                        <span>Analizi Başlat</span>
                                    </>
                                )}
                            </motion.button>

                            <AnimatePresence mode="wait">
                                {isAnalyzing ? (
                                    <motion.button
                                        key="cancel"
                                        initial={{ opacity: 0, scale: 0.8 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.8 }}
                                        whileHover={{ scale: 1.05 }}
                                        whileTap={{ scale: 0.95 }}
                                        onClick={async () => {
                                            try {
                                                await axios.post(`${API_URL}/cancel/${jobId}`);
                                                setIsAnalyzing(false);
                                            } catch (e) {
                                                alert("İptal hatası: " + e.message);
                                            }
                                        }}
                                        className="h-14 px-8 rounded-2xl font-bold flex items-center gap-2 bg-gradient-to-r from-red-600 to-pink-600 hover:from-red-500 hover:to-pink-600 text-white shadow-lg shadow-red-500/30 hover:shadow-red-500/50 transition-all"
                                    >
                                        <X className="w-5 h-5" /> İptal
                                    </motion.button>
                                ) : results.length > 0 ? (
                                    <motion.button
                                        key="clear"
                                        initial={{ opacity: 0, scale: 0.8 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.8 }}
                                        whileHover={{ scale: 1.05 }}
                                        whileTap={{ scale: 0.95 }}
                                        onClick={handleClearCache}
                                        className="h-14 px-6 rounded-2xl font-semibold flex items-center gap-2 bg-gradient-to-r from-slate-700 to-slate-800 hover:from-slate-600 hover:to-slate-800 text-white border-2 border-slate-600 hover:border-slate-500 shadow-lg transition-all"
                                    >
                                        <Trash2 className="w-5 h-5" /> Temizle ({results.length})
                                    </motion.button>
                                ) : null}
                            </AnimatePresence>
                        </div>

                        <AnimatePresence>
                            {isAnalyzing && (
                                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="space-y-4 pt-4">
                                    <div className="grid grid-cols-4 gap-4">
                                        <motion.div className="glass rounded-xl p-4 text-center border border-violet-500/20" whileHover={{ scale: 1.02, borderColor: 'rgba(139, 92, 246, 0.4)' }}>
                                            <div className="text-xs text-gray-400 mb-1">İlerleme</div>
                                            <div className="text-3xl font-bold bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">{Math.round(progress * 100)}%</div>
                                        </motion.div>
                                        <motion.div className="glass rounded-xl p-4 text-center border border-emerald-500/20" whileHover={{ scale: 1.02, borderColor: 'rgba(16, 185, 129, 0.4)' }}>
                                            <div className="text-xs text-gray-400 mb-1 flex items-center justify-center gap-1"><Clock className="w-3 h-3" /> Geçen Süre</div>
                                            <div className="text-3xl font-bold text-white">{formatTime(elapsedTime)}</div>
                                        </motion.div>
                                        <motion.div className="glass rounded-xl p-4 text-center border border-blue-500/20" whileHover={{ scale: 1.02, borderColor: 'rgba(59, 130, 246, 0.4)' }}>
                                            <div className="text-xs text-gray-400 mb-1 flex items-center justify-center gap-1"><Clock className="w-3 h-3 animate-pulse" /> Kalan Süre</div>
                                            <div className="text-3xl font-bold text-white">{formatTime(estimatedTime)}</div>
                                        </motion.div>
                                        <motion.div className="glass rounded-xl p-4 text-center border border-pink-500/20" whileHover={{ scale: 1.02, borderColor: 'rgba(236, 72, 153, 0.4)' }}>
                                            <div className="text-xs text-gray-400 mb-1">Durum</div>
                                            <div className="text-sm font-semibold text-white truncate">{status}</div>
                                        </motion.div>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </motion.div>

                <ResultsTable data={results} />
                </>
                ) : (
                    <motion.div 
                        initial={{ opacity: 0, y: 20 }} 
                        animate={{ opacity: 1, y: 0 }} 
                        transition={{ delay: 0.1 }}
                        className="glass rounded-3xl p-8 shadow-2xl"
                    >
                        <ReviewQueue apiKey={API_KEY} />
                    </motion.div>
                )}
            </div>
        </div>
    );
}
