import React, { useState, useEffect } from 'react';
import api from '../services/api';
import SharingModal from './SharingModal';
import { useUI } from '../context/UIContext';

/**
 * SessionDetailModal.jsx — Interactive Detail View for a Session
 */
const SessionDetailModal = ({ session, onClose, onUpdate }) => {
    const [docs, setDocs] = useState([]);
    const [loadingDocs, setLoadingDocs] = useState(false);
    const [updating, setUpdating] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [showSharingModal, setShowSharingModal] = useState(false);
    const { showAlert } = useUI();

    useEffect(() => {
        if (session?.subject_id) {
            fetchDocs();
        }
    }, [session?.subject_id]);

    const fetchDocs = async () => {
        try {
            setLoadingDocs(true);
            const res = await api.get(`/documents/${session.subject_id}`);
            setDocs(res.documents || []);
        } catch (err) {
            console.error('Error fetching docs:', err);
        } finally {
            setLoadingDocs(false);
        }
    };

    const handleStatusCycle = async () => {
        const statuses = ['todo', 'in_progress', 'done'];
        const currentIndex = statuses.indexOf(session.status || 'todo');
        const nextStatus = statuses[(currentIndex + 1) % statuses.length];
        await updateSession({ status: nextStatus });
    };

    const markComplete = async () => {
        await updateSession({ status: 'done' });
    };

    const updateSession = async (updates) => {
        try {
            setUpdating(true);
            if (updates.status === 'done') updates.is_done = true;
            const res = await api.patch(`/planning/${session.id}`, updates);
            onUpdate(res.session);
        } catch (err) {
            showAlert('Failed to update session', 'error');
        } finally {
            setUpdating(false);
        }
    };

    const toggleObjective = async (index) => {
        const newObjectives = [...session.key_objectives];
        newObjectives[index].done = !newObjectives[index].done;
        const allDone = newObjectives.every(obj => obj.done);
        const updates = { key_objectives: newObjectives };
        if (allDone && session.status !== 'done') {
            updates.status = 'done';
            updates.is_done = true;
        }
        await updateSession(updates);
    };

    const generateAiTasks = async (docId) => {
        try {
            setGenerating(true);
            const res = await api.post('/ai/ask', {
                document_id: docId,
                mode: 'tasks'
            });
            if (res.plan) {
                const updates = {
                    study_method: res.plan.method,
                    key_objectives: res.plan.tasks.map(t => ({ text: t, done: false })),
                    revision_tips: res.plan.tips,
                    is_ai_generated: true
                };
                await updateSession(updates);
                showAlert('Plan IA généré avec succès !', 'success');
            }
        } catch (err) {
            showAlert('Échec : ' + (err.error || err.message), 'error');
        } finally {
            setGenerating(false);
        }
    };

    if (!session) return null;

    const getStatusLabel = (s) => {
        if (s === 'todo') return 'À faire';
        if (s === 'in_progress') return 'En cours';
        return 'Terminé';
    };

    const doneCount = session.key_objectives?.filter(o => o.done).length || 0;
    const totalCount = session.key_objectives?.length || 0;
    const progressPct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="sdm-wrapper" onClick={e => e.stopPropagation()}>

                {/* ── Focus Banner ── */}
                <div className="sdm-focus-banner">
                    <span>📵</span>
                    <span>Laisse ton téléphone dans une autre pièce — Focus maximum !</span>
                </div>

                {/* ── Header ── */}
                <div className="sdm-header">
                    <div className="sdm-header-left">
                        <div className="sdm-title-row">
                            <h2 className="sdm-title">{session.subject_name}</h2>
                            <span className={`sdm-status-chip sdm-status-${session.status || 'todo'}`}>
                                {getStatusLabel(session.status)}
                            </span>
                        </div>
                        <p className="sdm-meta">
                            📅 {new Date(session.date).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}
                            &nbsp;•&nbsp;⏳ {session.duration_hours}h
                        </p>
                    </div>
                    <div className="sdm-header-right">
                        <button className="sdm-share-btn" onClick={() => setShowSharingModal(true)}>
                            🔗 Partager
                        </button>
                        <button className="sdm-close-btn" onClick={onClose}>×</button>
                    </div>
                </div>

                {/* ── Scrollable Body ── */}
                <div className="sdm-body">

                    {/* Section: Méthode d'étude */}
                    <section className="sdm-section">
                        <div className="sdm-section-header">
                            <h3 className="sdm-section-title">💡 Méthode d'étude</h3>
                            {docs.length > 0 && (
                                <button
                                    className={`sdm-ai-btn ${session.is_ai_generated ? 'sdm-ai-btn--done' : ''} ${generating ? 'sdm-ai-btn--loading' : ''}`}
                                    onClick={() => !session.is_ai_generated && !generating && generateAiTasks(docs[0].id)}
                                    disabled={generating || session.is_ai_generated}
                                >
                                    <span className="sdm-ai-btn-icon">
                                        {generating ? '⌛' : session.is_ai_generated ? '✅' : '✨'}
                                    </span>
                                    <span>
                                        {generating
                                            ? 'Optimisation en cours...'
                                            : session.is_ai_generated
                                            ? 'Optimisé par l\'IA'
                                            : 'Optimiser avec l\'IA'}
                                    </span>
                                </button>
                            )}
                        </div>
                        <p className="sdm-method-text">
                            {session.study_method || "Générez un plan d'étude IA pour commencer."}
                        </p>
                    </section>

                    {/* Section: Checklist */}
                    <section className="sdm-section">
                        <div className="sdm-section-header">
                            <h3 className="sdm-section-title">🎯 Checklist de révision</h3>
                            {totalCount > 0 && (
                                <span className="sdm-progress-label">{doneCount}/{totalCount}</span>
                            )}
                        </div>

                        {totalCount > 0 && (
                            <div className="sdm-progress-track">
                                <div
                                    className="sdm-progress-fill"
                                    style={{ width: `${progressPct}%` }}
                                />
                            </div>
                        )}

                        <div className="sdm-objectives">
                            {totalCount > 0 ? (
                                session.key_objectives.map((obj, i) => (
                                    <div
                                        key={i}
                                        className={`sdm-obj-row ${obj.done ? 'sdm-obj-row--done' : ''}`}
                                        onClick={() => toggleObjective(i)}
                                    >
                                        <div className={`sdm-checkbox ${obj.done ? 'sdm-checkbox--checked' : ''}`}>
                                            {obj.done && <span className="sdm-checkmark">✓</span>}
                                        </div>
                                        <label className="sdm-obj-label">{obj.text}</label>
                                    </div>
                                ))
                            ) : (
                                <p className="sdm-empty-hint">
                                    Utilisez l'IA pour générer une checklist à partir de vos PDFs.
                                </p>
                            )}
                        </div>
                    </section>

                    {/* Section: Conseils */}
                    {session.revision_tips?.length > 0 && (
                        <section className="sdm-section">
                            <h3 className="sdm-section-title">📌 Conseils Pratiques</h3>
                            <ul className="sdm-tips-list">
                                {session.revision_tips.map((tip, i) => (
                                    <li key={i} className="sdm-tip-item">
                                        <span className="sdm-tip-dot" />
                                        {tip}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {/* Section: PDFs liés */}
                    {docs.length > 0 && (
                        <section className="sdm-section">
                            <h3 className="sdm-section-title">📂 Supports de cours</h3>
                            <div className="sdm-docs-grid">
                                {docs.map(doc => (
                                    <a
                                        key={doc.id}
                                        href={`http://127.0.0.1:5001/api/documents/download/${doc.id}`}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="sdm-doc-card"
                                    >
                                        <span className="sdm-doc-icon">📄</span>
                                        <div className="sdm-doc-info">
                                            <span className="sdm-doc-name">{doc.original_name}</span>
                                            <span className="sdm-doc-action">Télécharger PDF ↓</span>
                                        </div>
                                    </a>
                                ))}
                            </div>
                        </section>
                    )}
                </div>

                {/* ── Footer ── */}
                <div className="sdm-footer">
                    <button
                        className={`sdm-cycle-btn sdm-cycle-${session.status || 'todo'}`}
                        onClick={handleStatusCycle}
                        disabled={updating}
                    >
                        <span className="sdm-cycle-icon">
                            {session.status === 'done' ? '✓' : session.status === 'in_progress' ? '▶' : '○'}
                        </span>
                        Statut : {getStatusLabel(session.status)}
                        <span className="sdm-cycle-hint">→ changer</span>
                    </button>

                    {session.status !== 'done' && (
                        <button
                            className="sdm-complete-btn"
                            onClick={markComplete}
                            disabled={updating}
                        >
                            ✓ Terminer la session
                        </button>
                    )}
                </div>

                {showSharingModal && (
                    <SharingModal
                        sessionToShare={session}
                        onClose={() => setShowSharingModal(false)}
                    />
                )}
            </div>
        </div>
    );
};

export default SessionDetailModal;
