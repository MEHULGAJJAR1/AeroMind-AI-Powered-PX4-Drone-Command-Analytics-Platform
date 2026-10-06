import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Check, ClipboardCheck, MapPin, Plus, Save, Send, Trash2 } from 'lucide-react';
import type { Telemetry, Waypoint } from '../types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { MapView } from '../components/MapView';
import { EmptyState, PageHeading, Panel, StatusBadge } from '../components/common';
import { api } from '../services/api';
import type { Mission } from '../types';

function routeLength(points: Waypoint[]) {
  const rad = (value: number) => value * Math.PI / 180;
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1]; const b = points[index];
    const dLat = rad(b.latitude - a.latitude); const dLon = rad(b.longitude - a.longitude);
    const value = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2;
    total += 6371000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }
  return total;
}

export function MissionPlannerPage({ telemetry }: { telemetry: Telemetry | null }) {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [name, setName] = useState('');
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [deleteDialog, setDeleteDialog] = useState(false);

  const selectedMission = missions.find((mission) => mission.id === selectedId) || null;
  const canUpload = telemetry?.source === 'px4' && telemetry.connected && !telemetry.armed && !telemetry.in_air;
  const distance = useMemo(() => routeLength(waypoints), [waypoints]);
  const load = async () => {
    setLoading(true);
    try {
      const data = await api.missions();
      setMissions(data);
      if (!selectedId && data.length) setSelectedId(data[0].id);
      setError('');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load missions'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!selectedMission) {
      setName(''); setWaypoints([]); return;
    }
    setName(selectedMission.name);
    setWaypoints(selectedMission.waypoints.map(({ latitude, longitude, altitude_m, hold_time_s }) => ({ latitude, longitude, altitude_m, hold_time_s })));
  }, [selectedId, selectedMission?.updated_at]);

  const addWaypoint = (latitude?: number, longitude?: number) => {
    const current = telemetry?.latitude != null && telemetry.longitude != null ? [telemetry.latitude, telemetry.longitude] : [47.397742, 8.545594];
    const baseLat = latitude ?? current[0] + waypoints.length * 0.00012;
    const baseLon = longitude ?? current[1] + waypoints.length * 0.00012;
    setWaypoints((currentPoints) => [...currentPoints, { latitude: Number(baseLat.toFixed(6)), longitude: Number(baseLon.toFixed(6)), altitude_m: 30, hold_time_s: 0 }]);
    setNotice('');
  };
  const updatePoint = (index: number, key: keyof Waypoint, value: number) => setWaypoints((current) => current.map((point, pointIndex) => pointIndex === index ? { ...point, [key]: value } : point));
  const movePoint = (index: number, direction: -1 | 1) => setWaypoints((current) => {
    const next = [...current]; const target = index + direction;
    if (target < 0 || target >= next.length) return current;
    [next[index], next[target]] = [next[target], next[index]];
    return next;
  });
  const removePoint = (index: number) => setWaypoints((current) => current.filter((_, pointIndex) => pointIndex !== index));

  const createMission = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const mission = await api.createMission('New mission', []);
      setMissions((current) => [mission, ...current]);
      setSelectedId(mission.id);
      setNotice('Draft created. Add waypoints, then save the route.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not create mission'); }
    finally { setBusy(false); }
  };
  const saveMission = async () => {
    if (!selectedId) return;
    if (!name.trim()) { setError('Enter a mission name before saving.'); return; }
    if (waypoints.some((point) => !Number.isFinite(point.latitude) || !Number.isFinite(point.longitude) || !Number.isFinite(point.altitude_m) || !Number.isFinite(point.hold_time_s))) { setError('Every waypoint needs valid numeric coordinates, altitude and hold time.'); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      const saved = await api.updateMission(selectedId, name.trim(), waypoints.map(({ latitude, longitude, altitude_m, hold_time_s }) => ({ latitude, longitude, altitude_m, hold_time_s })));
      setMissions((current) => current.map((mission) => mission.id === saved.id ? saved : mission));
      setNotice(`Saved ${saved.waypoints.length} waypoint${saved.waypoints.length === 1 ? '' : 's'} to draft.`);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not save mission'); }
    finally { setBusy(false); }
  };
  const upload = async () => {
    if (!selectedId) return;
    if (waypoints.length < 2) { setError('Upload requires at least two waypoints.'); return; }
    if (waypoints.some((point) => point.altitude_m <= 0 || point.altitude_m > 120 || point.latitude < -90 || point.latitude > 90 || point.longitude < -180 || point.longitude > 180 || point.hold_time_s < 0)) { setError('Resolve coordinate, altitude or hold-time validation errors before upload.'); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      await api.updateMission(selectedId, name.trim(), waypoints.map(({ latitude, longitude, altitude_m, hold_time_s }) => ({ latitude, longitude, altitude_m, hold_time_s })));
      const result = await api.uploadMission(selectedId);
      setNotice(result.message);
      await load();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Mission upload failed'); }
    finally { setBusy(false); }
  };
  const deleteMission = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api.deleteMission(selectedId);
      const next = missions.filter((mission) => mission.id !== selectedId);
      setMissions(next);
      setSelectedId(next[0]?.id || '');
      setDeleteDialog(false);
      setNotice('Mission deleted.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not delete mission'); }
    finally { setBusy(false); }
  };

  return <>
    <PageHeading eyebrow="Autonomous workflow" title="Mission planner" description="Build an ordered route, review it on the map, validate it and upload to PX4 while disarmed." action={<button className="button-primary" disabled={busy} onClick={() => void createMission()}><Plus size={15} />New mission</button>} />
    {error && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
    {notice && <div role="status" className="mb-4 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.06] px-3 py-2 text-xs text-emerald-200">{notice}</div>}
    {telemetry?.source === 'mock' && <div className="mb-4 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">Mock mode: drafts can be edited and saved, but upload and vehicle commands require a live PX4 connection.</div>}
    <div className="grid gap-5 xl:grid-cols-[1.55fr_.85fr]">
      <div className="space-y-5">
        <Panel title="Route map" subtitle="Click the map to add a waypoint; the route is saved only when you choose Save draft." action={<StatusBadge tone={selectedMission?.status === 'uploaded' ? 'good' : 'neutral'}>{selectedMission?.status || 'new draft'}</StatusBadge>} className="!p-3 sm:!p-4">
          <MapView telemetry={telemetry} waypoints={waypoints} onMapClick={(lat, lon) => addWaypoint(lat, lon)} height="h-[350px] sm:h-[440px]" />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-[10px] text-slate-500"><span>{waypoints.length} waypoint{waypoints.length === 1 ? '' : 's'} · route {distance >= 1000 ? `${(distance / 1000).toFixed(2)} km` : `${distance.toFixed(0)} m`}</span><span>Altitudes are relative to home</span></div>
        </Panel>
        <Panel title="Waypoints" subtitle="Reorder the route or edit position, altitude and hold time." action={<button className="button-secondary !px-2.5 !py-2" disabled={!selectedId} onClick={() => addWaypoint()}><Plus size={13} />Add current-area point</button>}>
          {!selectedId ? <EmptyState title="Select or create a mission" message="Mission waypoints are stored as drafts until uploaded to PX4." /> : waypoints.length === 0 ? <EmptyState icon={<MapPin size={21} />} title="No waypoints yet" message="Click the route map or add a point near the current vehicle position." action={<button className="button-secondary" onClick={() => addWaypoint()}><Plus size={13} />Add waypoint</button>} /> : <div className="space-y-2">
            {waypoints.map((point, index) => <div key={`waypoint-${index}`} className="rounded-xl border border-slate-800 bg-slate-900/45 p-3">
              <div className="mb-3 flex items-center justify-between"><div className="flex items-center gap-2"><span className="flex h-6 w-6 items-center justify-center rounded-md bg-violet-400/10 text-[10px] font-bold text-violet-300">{String(index + 1).padStart(2, '0')}</span><span className="text-[11px] font-semibold text-slate-200">Waypoint {index + 1}</span></div><div className="flex items-center"><button className="icon-button !h-7 !w-7" title="Move up" aria-label={`Move waypoint ${index + 1} up`} disabled={index === 0} onClick={() => movePoint(index, -1)}><ArrowUp size={13} /></button><button className="icon-button !h-7 !w-7" title="Move down" aria-label={`Move waypoint ${index + 1} down`} disabled={index === waypoints.length - 1} onClick={() => movePoint(index, 1)}><ArrowDown size={13} /></button><button className="icon-button !h-7 !w-7 text-rose-300" title="Delete waypoint" aria-label={`Delete waypoint ${index + 1}`} onClick={() => removePoint(index)}><Trash2 size={13} /></button></div></div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">{([['latitude', 'Latitude', -90, 90, 0.000001], ['longitude', 'Longitude', -180, 180, 0.000001], ['altitude_m', 'Altitude · m', 1, 120, 1], ['hold_time_s', 'Hold · sec', 0, 3600, 1]] as const).map(([key, label, min, max, step]) => <label key={key}><span className="field-label !text-[9px]">{label}</span><input className="field !px-2 !py-2 font-mono !text-[11px]" type="number" min={min} max={max} step={step} value={point[key]} onChange={(event) => updatePoint(index, key, Number(event.target.value))} /></label>)}</div>
            </div>)}
          </div>}
        </Panel>
      </div>
      <div className="space-y-5">
        <Panel title="Mission details" subtitle="Saved missions are private to your operator account.">
          {loading ? <p className="py-4 text-xs text-slate-500">Loading missions…</p> : <><label className="field-label" htmlFor="mission-select">Saved mission</label><select id="mission-select" className="field mb-4" value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setError(''); setNotice(''); }}><option value="">Select mission…</option>{missions.map((mission) => <option key={mission.id} value={mission.id}>{mission.name} · {mission.status}</option>)}</select></>}
          {selectedId && <><label className="field-label" htmlFor="mission-name">Mission name</label><input id="mission-name" className="field" value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /><div className="mt-4 grid grid-cols-2 gap-2"><div className="rounded-lg bg-slate-900/70 p-3"><span className="text-[9px] uppercase tracking-wider text-slate-600">Waypoints</span><p className="mt-1 text-lg font-semibold text-white">{waypoints.length}</p></div><div className="rounded-lg bg-slate-900/70 p-3"><span className="text-[9px] uppercase tracking-wider text-slate-600">Route distance</span><p className="mt-1 text-lg font-semibold text-white">{distance >= 1000 ? `${(distance / 1000).toFixed(1)} km` : `${distance.toFixed(0)} m`}</p></div></div><div className="mt-4 space-y-2"><button className="button-secondary w-full" disabled={busy} onClick={() => void saveMission()}><Save size={14} />Save draft</button><button className="button-primary w-full" disabled={busy || !canUpload || waypoints.length < 2} onClick={() => void upload()}><Send size={14} />{busy ? 'Working…' : 'Validate & upload to PX4'}</button>{!canUpload && <p className="text-center text-[10px] leading-4 text-slate-600">Upload requires connected PX4, disarmed and on the ground.</p>}<button className="button-secondary w-full border-rose-400/15 text-rose-300 hover:bg-rose-400/10" disabled={busy} onClick={() => setDeleteDialog(true)}><Trash2 size={13} />Delete mission</button></div></>}
        </Panel>
        <Panel title="Pre-upload validation" subtitle="Backend repeats validation before sending a mission">
          <div className="space-y-3">{[
            [waypoints.length >= 2, 'At least two waypoints'],
            [waypoints.length <= 100, 'Within 100-waypoint limit'],
            [waypoints.every((point) => point.latitude >= -90 && point.latitude <= 90 && point.longitude >= -180 && point.longitude <= 180), 'Valid latitude / longitude'],
            [waypoints.every((point) => point.altitude_m > 0 && point.altitude_m <= 120), 'Altitude 1–120 m AGL'],
            [telemetry?.source === 'px4' && telemetry.connected, 'Live PX4 / MAVSDK link'],
            [Boolean(telemetry?.connected && !telemetry.armed && !telemetry.in_air), 'Vehicle disarmed and grounded'],
          ].map(([valid, label]) => <div key={String(label)} className="flex items-center gap-2 text-xs"><span className={`flex h-5 w-5 items-center justify-center rounded-full ${valid ? 'bg-accent/10 text-accent' : 'bg-slate-800 text-slate-600'}`}>{valid ? <Check size={12} /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}</span><span className={valid ? 'text-slate-300' : 'text-slate-500'}>{label}</span></div>)}</div>
          <div className="mt-4 rounded-lg border border-cyan-400/10 bg-cyan-400/[0.04] p-3 text-[10px] leading-5 text-cyan-100/60"><ClipboardCheck size={13} className="mr-1.5 inline text-cyan-300" />Waypoint hold time is encoded using MAVLink NAV_WAYPOINT loiter-time. Verify route, altitude reference and failsafes in QGroundControl before starting.</div>
        </Panel>
      </div>
    </div>
    {deleteDialog && <ConfirmDialog title="Delete this mission?" message="This permanently deletes the saved mission and its waypoints. This action cannot be undone." confirmLabel="Delete mission" busy={busy} onCancel={() => setDeleteDialog(false)} onConfirm={() => void deleteMission()} />}
  </>;
}
