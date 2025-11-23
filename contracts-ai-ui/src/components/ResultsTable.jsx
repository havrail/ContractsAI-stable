import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { FileText, Calendar, MapPin, User, Building2, CheckCircle2, Eye } from 'lucide-react';
import PDFPreview from './PDFPreview';

export default function ResultsTable({ data }) {
    const [previewFile, setPreviewFile] = useState(null);

    if (!data || data.length === 0) return null;

    return (
        <>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="space-y-4"
            >
                <div className="flex items-center gap-3 mb-6">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold text-white">Analiz Sonuçları</h2>
                        <p className="text-sm text-gray-400">{data.length} sözleşme işlendi</p>
                    </div>
                </div>

                <div className="grid gap-4">
                    {data.map((row, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.05 }}
                            className="glass rounded-2xl p-6 hover:bg-slate-800/40 transition-all group"
                        >
                            <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
                                {/* File Info */}
                                <div className="space-y-1">
                                    <div className="text-xs font-semibold text-violet-400 uppercase tracking-wider">Dosya</div>
                                    <div className="text-white font-medium truncate group-hover:text-violet-300 transition-colors">
                                        {row.dosya_adi}
                                    </div>
                                    <div className="text-xs text-gray-500">{row.doc_type}</div>
                                    {/* Preview Button */}
                                    <button
                                        onClick={() => setPreviewFile(row.dosya_adi)}
                                        className="mt-2 flex items-center gap-1.5 px-3 py-1.5 bg-blue-600/20 text-blue-400 rounded-lg hover:bg-blue-600/30 transition-colors text-sm"
                                    >
                                        <Eye className="w-4 h-4" />
                                        <span>Önizle</span>
                                    </button>
                                </div>

                                {/* Contract Info */}
                                <div className="space-y-1">
                                    <div className="text-xs font-semibold text-fuchsia-400 uppercase tracking-wider">Sözleşme</div>
                                    <div className="text-white font-medium">{row.contract_name || "—"}</div>
                                    <div className="flex items-center gap-1.5 text-sm text-gray-400">
                                        <Building2 className="w-3.5 h-3.5" />
                                        <span>{row.company_type || "—"}</span>
                                    </div>
                                </div>

                                {/* Party Info */}
                                <div className="space-y-1">
                                    <div className="text-xs font-semibold text-cyan-400 uppercase tracking-wider">Karşı Taraf</div>
                                    <div className="text-white flex items-center gap-1.5">
                                        <User className="w-3.5 h-3.5 text-cyan-400" />
                                        <span className="font-medium">{row.signing_party || "—"}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5 text-sm text-gray-400">
                                        <MapPin className="w-3.5 h-3.5" />
                                        <span>{row.country || "—"}</span>
                                    </div>
                                </div>

                                {/* Address & Date */}
                                <div className="space-y-1">
                                    <div className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Detaylar</div>
                                    <div className="text-sm text-white line-clamp-2">{row.address || "—"}</div>
                                    <div className="flex items-center gap-1.5 text-sm text-gray-400">
                                        <Calendar className="w-3.5 h-3.5" />
                                        <span>{row.signed_date || "—"}</span>
                                    </div>
                                </div>

                                {/* Status */}
                                <div className="space-y-1">
                                    <div className="text-xs font-semibold text-pink-400 uppercase tracking-wider">Durum</div>
                                    <div className="flex items-center gap-2">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                        <span className="text-white font-medium">{row.signature}</span>
                                    </div>
                                    <div className="text-xs text-gray-500">{row.telenity_entity || "—"}</div>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </motion.div>

            {/* PDF Preview Modal */}
            {previewFile && (
                <PDFPreview
                    pdfUrl={`http://localhost:8000/api/pdf/${previewFile}`}
                    onClose={() => setPreviewFile(null)}
                />
            )}
        </>
    );
}
