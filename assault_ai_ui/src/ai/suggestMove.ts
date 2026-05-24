export function suggestMove(units: any[], state: any) {
    if (!units || units.length === 0) {
        return null;
    }

    // simple fallback: pick first available unit
    return {
        type: "WaitAction",
        unit_id: units[0].unit_id,
    };
}