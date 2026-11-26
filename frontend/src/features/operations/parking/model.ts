export interface Space {
  id: number; code: string; is_active: boolean; available?: boolean; occupied?: boolean;
}
export interface Vehicle { id: number; plate: string; guest: number; guest_name?: string; allocated?: boolean }
export interface Allocation {
  id: number; space: number; space_code?: string; vehicle: number; vehicle_plate?: string; guest?: number; guest_name?: string;
  started_at: string; ended_at: string | null;
}
export const spaceLabel = (s: Space) => `Space ${s.code}`;
export const vehicleLabel = (v: Vehicle) => `${v.plate} · ${v.guest_name || `Guest #${v.guest}`}`;
export const spaceOf = (a: Allocation) => a.space_code ? `Space ${a.space_code}` : `Space ID ${a.space}`;
export const vehicleOf = (a: Allocation) => a.vehicle_plate || `Vehicle #${a.vehicle}`;
export const selectableSpace = (s: Space) => s.is_active && s.occupied !== true && s.available !== false;
