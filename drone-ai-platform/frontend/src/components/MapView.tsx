import { useEffect, useMemo, useRef } from 'react';
import L from 'leaflet';
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import type { Telemetry, Waypoint } from '../types';

export interface MapPoint {
  latitude: number | null;
  longitude: number | null;
}

function FollowPosition({ point }: { point: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (point) map.setView(point, Math.max(map.getZoom(), 15), { animate: true });
  }, [map, point?.[0], point?.[1]]);
  return null;
}

function InitialPosition({ point }: { point: [number, number] | null }) {
  const map = useMap();
  const centered = useRef(false);
  useEffect(() => {
    if (point && !centered.current) {
      map.setView(point, 15, { animate: false });
      centered.current = true;
    }
  }, [map, point?.[0], point?.[1]]);
  return null;
}

function ClickHandler({ onClick }: { onClick?: (latitude: number, longitude: number) => void }) {
  useMapEvents({ click: (event) => onClick?.(event.latlng.lat, event.latlng.lng) });
  return null;
}

export function MapView({
  telemetry,
  waypoints = [],
  history = [],
  follow = false,
  onMapClick,
  height = 'h-[320px]',
  className = '',
}: {
  telemetry: Telemetry | null;
  waypoints?: Waypoint[];
  history?: Telemetry[];
  follow?: boolean;
  onMapClick?: (latitude: number, longitude: number) => void;
  height?: string;
  className?: string;
}) {
  const home = telemetry?.home_position;
  const position = telemetry?.latitude != null && telemetry.longitude != null ? [telemetry.latitude, telemetry.longitude] as [number, number] : null;
  const homePoint: [number, number] | null = home ? [home.latitude, home.longitude] : null;
  const center: [number, number] = position || homePoint || [47.397742, 8.545594];
  const routePoints = useMemo(() => waypoints.map((point) => [point.latitude, point.longitude] as [number, number]), [waypoints]);
  const track = useMemo(() => {
    const points = history.filter((item) => item.latitude != null && item.longitude != null).map((item) => [item.latitude as number, item.longitude as number] as [number, number]);
    if (position && (points.length === 0 || points[points.length - 1][0] !== position[0] || points[points.length - 1][1] !== position[1])) points.push(position);
    return points.slice(-180);
  }, [history, position?.[0], position?.[1]]);
  const heading = telemetry?.heading_deg ?? 0;
  const droneIcon = useMemo(() => L.divIcon({
    className: 'drone-marker-shell',
    html: `<div class="drone-marker" style="transform:rotate(${heading}deg)"><svg viewBox="0 0 24 24" width="25" height="25" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2.5 19.2 20l-7.2-4.2L4.8 20 12 2.5Z" fill="#64e4b6" stroke="#07131a" stroke-width="1.4" stroke-linejoin="round"/></svg></div>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
  }), [heading]);

  return <div className={`map-shell relative overflow-hidden rounded-xl border border-slate-700/60 ${height} ${className}`}>
    <MapContainer center={center} zoom={15} scrollWheelZoom className="h-full w-full" attributionControl>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {follow ? <FollowPosition point={position} /> : <InitialPosition point={position} />}
      <ClickHandler onClick={onMapClick} />
      {homePoint && <CircleMarker center={homePoint} radius={7} pathOptions={{ color: '#67a4ff', fillColor: '#67a4ff', fillOpacity: 0.85 }}><Tooltip>Home position</Tooltip></CircleMarker>}
      {track.length > 1 && <Polyline positions={track} pathOptions={{ color: '#64e4b6', weight: 3, opacity: 0.68 }} />}
      {routePoints.length > 1 && <Polyline positions={routePoints} pathOptions={{ color: '#ab91ff', weight: 3, dashArray: '7 8', opacity: 0.9 }} />}
      {waypoints.map((point, index) => <CircleMarker key={point.id || `wp-${index}`} center={[point.latitude, point.longitude]} radius={8} pathOptions={{ color: '#c5b5ff', fillColor: '#9d7cff', fillOpacity: 0.9, weight: 2 }}><Tooltip>Waypoint {index + 1} · {point.altitude_m} m</Tooltip></CircleMarker>)}
      {position && <Marker position={position} icon={droneIcon}><Tooltip direction="top">{telemetry?.source === 'mock' ? 'Simulated vehicle' : 'PX4 vehicle'} · heading {heading.toFixed(0)}°</Tooltip></Marker>}
    </MapContainer>
    <div className="pointer-events-none absolute left-3 top-3 z-[500] flex items-center gap-2 rounded-lg border border-slate-700/80 bg-slate-950/85 px-3 py-2 text-[10px] text-slate-300 shadow-lg backdrop-blur">
      <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_9px_#64e4b6]" />{telemetry?.source === 'mock' ? 'SIMULATED POSITION' : 'LIVE MAP'}
    </div>
    {onMapClick && <div className="pointer-events-none absolute bottom-3 right-3 z-[500] rounded-md bg-slate-950/85 px-2.5 py-1.5 text-[10px] text-slate-300">Click map to add waypoint</div>}
  </div>;
}
