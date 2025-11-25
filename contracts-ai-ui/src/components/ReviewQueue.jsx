import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { AlertCircle, CheckCircle, XCircle, Edit2, Save, X, ChevronDown, ChevronUp } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_URL = "http://localhost:8000";

export default function ReviewQueue({ apiKey }) {
    const [pendingContracts, setPendingContracts] = useState([]);
    const [loading, setLoading] = useState(false);
    const [expandedContract, setExpandedContract] = useState(null);
    const [editingField, setEditingField] = useState(null);
    const [editValue, setEditValue] = useState('');
    const [userName, setUserName] = useState('reviewer');

    useEffect(() => {
        fetchPendingReviews();
    }, []);

    const fetchPendingReviews = async () => {
        setLoading(true);
        try {
            const res = await axios.get(`${API_URL}/api/review/pending`, {
                headers: { 'X-API-Key': apiKey }
            });
            setPendingContracts(res.data.contracts);
        } catch (error) {
            console.error('Failed to fetch pending reviews:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleReview = async (contractId, status) => {
        try {
            await axios.post(
                `${API_URL}/api/review/${contractId}`,
                {
                    review_status: status,
                    reviewed_by: userName
                },
                { headers: { 'X-API-Key': apiKey } }
            );
            
            // Remove from list
            setPendingContracts(prev => prev.filter(c => c.id !== contractId));
        } catch (error) {
            console.error('Review failed:', error);
            alert('Review failed: ' + error.message);
        }
    };

    const startEditing = (contractId, fieldName, currentValue) => {
        setEditingField({ contractId, fieldName });
        setEditValue(currentValue || '');
    };

    const cancelEditing = () => {
        setEditingField(null);
        setEditValue('');
    };

    const saveEdit = async (contract) => {
        if (!editingField) return;

        const { contractId, fieldName } = editingField;
        const oldValue = contract[fieldName];

        try {
            await axios.post(
                `${API_URL}/api/correct/${contractId}`,
                {
                    field_name: fieldName,
                    new_value: editValue,
                    old_value: oldValue,
                    corrected_by: userName,
                    reason: 'Manual correction from review'
                },
                { headers: { 'X-API-Key': apiKey } }
            );

            // Update local state
            setPendingContracts(prev => 
                prev.map(c => 
                    c.id === contractId 
                        ? { ...c, [fieldName]: editValue }
                        : c
                )
            );

            cancelEditing();
        } catch (error) {
            console.error('Correction failed:', error);
            alert('Correction failed: ' + error.message);
        }
    };

    const getConfidenceColor = (score) => {
        if (score >= 90) return 'text-green-400';
        if (score >= 75) return 'text-blue-400';
        if (score >= 60) return 'text-yellow-400';
        return 'text-red-400';
    };

    const getConfidenceLabel = (score) => {
        if (score >= 90) return 'Excellent';
        if (score >= 75) return 'Good';
        if (score >= 60) return 'Acceptable';
        return 'Low';
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto mb-4"></div>
                    <p className="text-gray-400">Loading reviews...</p>
                </div>
            </div>
        );
    }

    if (pendingContracts.length === 0) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-center">
                    <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
                    <h3 className="text-xl font-semibold mb-2">All Caught Up!</h3>
                    <p className="text-gray-400">No contracts pending review</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h2 className="text-2xl font-bold text-white">Review Queue</h2>
                    <p className="text-gray-400 mt-1">
                        {pendingContracts.length} contract{pendingContracts.length !== 1 ? 's' : ''} need review
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <input
                        type="text"
                        placeholder="Your name"
                        value={userName}
                        onChange={(e) => setUserName(e.target.value)}
                        className="px-3 py-1 bg-slate-800 border border-slate-700 rounded text-sm focus:outline-none focus:border-purple-500"
                    />
                </div>
            </div>

            {/* Contract Cards */}
            <div className="space-y-3">
                {pendingContracts.map((contract) => {
                    const isExpanded = expandedContract === contract.id;
                    
                    return (
                        <motion.div
                            key={contract.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="glass rounded-lg overflow-hidden border border-slate-700/50"
                        >
                            {/* Compact View */}
                            <div 
                                className="p-4 cursor-pointer hover:bg-slate-800/30 transition-colors"
                                onClick={() => setExpandedContract(isExpanded ? null : contract.id)}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            <AlertCircle className="h-5 w-5 text-yellow-500 flex-shrink-0" />
                                            <h3 className="font-semibold text-white">{contract.dosya_adi}</h3>
                                        </div>
                                        <div className="flex items-center gap-4 text-sm text-gray-400 ml-8">
                                            <span>{contract.signing_party || 'Unknown Party'}</span>
                                            <span>•</span>
                                            <span className={getConfidenceColor(contract.confidence_score)}>
                                                {contract.confidence_score}% ({getConfidenceLabel(contract.confidence_score)})
                                            </span>
                                            {contract.validation_issues > 0 && (
                                                <>
                                                    <span>•</span>
                                                    <span className="text-red-400">
                                                        {contract.validation_issues} issue{contract.validation_issues !== 1 ? 's' : ''}
                                                    </span>
                                                </>
                                            )}
                                        </div>
                                        <p className="text-sm text-yellow-500 ml-8 mt-1">
                                            Reason: {contract.review_reason}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {isExpanded ? (
                                            <ChevronUp className="h-5 w-5 text-gray-400" />
                                        ) : (
                                            <ChevronDown className="h-5 w-5 text-gray-400" />
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Expanded View */}
                            <AnimatePresence>
                                {isExpanded && (
                                    <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: 'auto', opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                        className="border-t border-slate-700/50"
                                    >
                                        <div className="p-4 space-y-4 bg-slate-900/30">
                                            {/* Editable Fields */}
                                            {['signing_party', 'contract_name', 'signed_date', 'address', 'country'].map(field => {
                                                const isEditing = editingField?.contractId === contract.id && editingField?.fieldName === field;
                                                const value = contract[field];
                                                
                                                return (
                                                    <div key={field} className="grid grid-cols-4 gap-4 items-start">
                                                        <label className="text-sm font-medium text-gray-400 capitalize">
                                                            {field.replace('_', ' ')}:
                                                        </label>
                                                        <div className="col-span-3 flex items-center gap-2">
                                                            {isEditing ? (
                                                                <>
                                                                    <input
                                                                        type="text"
                                                                        value={editValue}
                                                                        onChange={(e) => setEditValue(e.target.value)}
                                                                        className="flex-1 px-3 py-1.5 bg-slate-800 border border-slate-600 rounded focus:outline-none focus:border-purple-500"
                                                                        autoFocus
                                                                    />
                                                                    <button
                                                                        onClick={() => saveEdit(contract)}
                                                                        className="p-1.5 bg-green-600 hover:bg-green-700 rounded transition-colors"
                                                                    >
                                                                        <Save className="h-4 w-4" />
                                                                    </button>
                                                                    <button
                                                                        onClick={cancelEditing}
                                                                        className="p-1.5 bg-gray-600 hover:bg-gray-700 rounded transition-colors"
                                                                    >
                                                                        <X className="h-4 w-4" />
                                                                    </button>
                                                                </>
                                                            ) : (
                                                                <>
                                                                    <span className={`flex-1 ${!value ? 'text-gray-500 italic' : 'text-white'}`}>
                                                                        {value || 'Not extracted'}
                                                                    </span>
                                                                    <button
                                                                        onClick={() => startEditing(contract.id, field, value)}
                                                                        className="p-1.5 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
                                                                    >
                                                                        <Edit2 className="h-4 w-4" />
                                                                    </button>
                                                                </>
                                                            )}
                                                        </div>
                                                    </div>
                                                );
                                            })}

                                            {/* Action Buttons */}
                                            <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-700/50">
                                                <button
                                                    onClick={() => handleReview(contract.id, 'rejected')}
                                                    className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg flex items-center gap-2 transition-colors"
                                                >
                                                    <XCircle className="h-4 w-4" />
                                                    Reject
                                                </button>
                                                <button
                                                    onClick={() => handleReview(contract.id, 'approved')}
                                                    className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg flex items-center gap-2 transition-colors"
                                                >
                                                    <CheckCircle className="h-4 w-4" />
                                                    Approve
                                                </button>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    );
                })}
            </div>
        </div>
    );
}
