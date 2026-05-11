// EntitySpawners.js — shared live capture of oCEntityCpntEntitySpawner
// instances constructed since the hook was armed.
//
// The hook attaches at IIFE time. SETUP-BOUND: load BEFORE the chapter
// you want to capture — the hook only fires on future ctor invocations.
// Loading mid-chapter yields zero captures for that chapter.
//
// What's captured: every `oCEntityCpntEntitySpawner` (the universal spawn
// component, ctor at RVA 0x2d0ee0). Every "[Entity spawner] X" anchor in
// the game bears one — hourglass, cauldron sub-spawners, teleporter plate,
// enemy camps, destructible barrels / crates, fireflies, boss arena
// spawners, etc. Not narrowed by purpose; it's the underlying primitive.
//
// Read-only from a consumer's perspective. Powers that need spawner data
// auto-load this util in their IIFE — the user never has to know about it.
//
// REPL surface (after loadUtil("EntitySpawners")):
//   EntitySpawners._all              array of NativePointer (raw)
//   EntitySpawners.size()            number — count of captures
//   EntitySpawners.find(name)        {ptr, parent, parentName, parentLoc} | null
//                                    first capture whose parentName contains name
//                                    (case-insensitive substring)
//   EntitySpawners.filter(name)      array of matches (same record shape)
//
// Composition: this hook stacks with any other Interceptor on the same
// RVA (e.g. Hourglass / SpawnerProbe each have their own). Frida fires
// each independently. There's no ordering or conflict — they're just
// duplicated effort. Future cleanup is to migrate the others to read
// from this util.

(function () {
    'use strict';

    var version = "0.1.0";

    var rwMod = Process.findModuleByName('Ravenswatch.exe');
    if (!rwMod) { console.log('[EntitySpawners] FATAL: no Ravenswatch.exe'); return; }
    var IMG = rwMod.base;

    var SPAWNER_CTOR_RVA       = 0x2d0ee0;   // FUN_1402d0ee0 — oCEntityCpntEntitySpawner ctor
    var SPAWNER_PARENT_OFF     = 0x08;       // spawner+0x08 = parent oCEntity*
    var ENTITY_POS_OFF         = 0x324;      // entity+0x324 = vec3 position
    var ENTITY_SETTINGS_OFF    = 0x28;       // entity+0x28 = oCEntitySettings*
    var SETTINGS_NAME_PTR_OFF  = 0x08;       // settings+0x08 = char* name
    var SETTINGS_NAME_LEN_OFF  = 0x10;       // settings+0x10 = u32 length

    if (!RW.EntitySpawners) RW.EntitySpawners = {};
    var ES = RW.EntitySpawners;

    // Re-load safety: detach prior hook + clear capture list before re-arming.
    if (ES._ctorHook) {
        try { ES._ctorHook.detach(); } catch (e) {}
        ES._ctorHook = null;
    }
    ES._all = [];

    ES._ctorHook = Interceptor.attach(IMG.add(SPAWNER_CTOR_RVA), {
        onEnter: function (args) {
            try { ES._all.push(ptr(args[0])); }
            catch (e) {}
        }
    });

    function readParentName(parent) {
        try {
            var s = parent.add(ENTITY_SETTINGS_OFF).readPointer();
            if (!s || s.isNull() || s.toString() === '0xffffffffffffffff') return null;
            var nPtr = s.add(SETTINGS_NAME_PTR_OFF).readPointer();
            var nLen = s.add(SETTINGS_NAME_LEN_OFF).readU32();
            if (!nPtr || nPtr.isNull() || nLen === 0 || nLen >= 256) return null;
            return nPtr.readUtf8String(nLen);
        } catch (e) { return null; }
    }

    function readVec3(p) {
        try {
            return { x: p.readFloat(), y: p.add(4).readFloat(), z: p.add(8).readFloat() };
        } catch (e) { return null; }
    }

    function buildRecord(spawnerPtr) {
        var parent;
        try { parent = spawnerPtr.add(SPAWNER_PARENT_OFF).readPointer(); }
        catch (e) { return null; }
        if (!parent || parent.isNull() || parent.toString() === '0xffffffffffffffff') return null;
        var name = readParentName(parent);
        if (!name) return null;
        var loc = readVec3(parent.add(ENTITY_POS_OFF));
        return { ptr: spawnerPtr, parent: parent, parentName: name, parentLoc: loc };
    }

    /*
     * ----------------------------------------------------------------
     * EntitySpawners.size(): number
     *
     * Count of captured spawner-component instances since the hook
     * armed. Zero before the chapter loads (hook armed but no ctors
     * fired yet).
     * ----------------------------------------------------------------
     */
    ES.size = function () {
        return ES._all.length;
    };

    /*
     * ----------------------------------------------------------------
     * EntitySpawners.find(parentNameSubstring: string):
     *   {ptr, parent, parentName, parentLoc} | null
     *
     * First capture whose parent entity's settings name contains the
     * given substring (case-insensitive). Returns a record with the
     * raw spawner pointer, parent oCEntity pointer, the resolved
     * parent name string, and the parent's vec3 position.
     *
     * Use cases: locating named landmarks (e.g. find("teleporter_start"),
     * find("noModel+2Cpnt")) without re-implementing the parent/settings
     * walk in every consumer.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Linear scan over ES._all. For each spawner pointer, dereferences
     *   parent at +0x08, reads parent's oCEntitySettings at parent+0x28,
     *   reads name from settings+0x08 (char*) / +0x10 (length). Substring
     *   matches lowercased. Reads parent+0x324 for position vec3.
     */
    ES.find = function (parentNameSubstring) {
        if (typeof parentNameSubstring !== 'string' || !parentNameSubstring.length) {
            console.log("[EntitySpawners.find] need a non-empty substring");
            return null;
        }
        var needle = parentNameSubstring.toLowerCase();
        for (var i = 0; i < ES._all.length; i++) {
            var rec = buildRecord(ES._all[i]);
            if (!rec) continue;
            if (rec.parentName.toLowerCase().indexOf(needle) >= 0) return rec;
        }
        return null;
    };

    /*
     * ----------------------------------------------------------------
     * EntitySpawners.filter(parentNameSubstring: string):
     *   array of {ptr, parent, parentName, parentLoc}
     *
     * Every capture whose parentName contains the substring (case-
     * insensitive). Same record shape as find().
     * ----------------------------------------------------------------
     */
    ES.filter = function (parentNameSubstring) {
        if (typeof parentNameSubstring !== 'string' || !parentNameSubstring.length) {
            console.log("[EntitySpawners.filter] need a non-empty substring");
            return [];
        }
        var needle = parentNameSubstring.toLowerCase();
        var out = [];
        for (var i = 0; i < ES._all.length; i++) {
            var rec = buildRecord(ES._all[i]);
            if (!rec) continue;
            if (rec.parentName.toLowerCase().indexOf(needle) >= 0) out.push(rec);
        }
        return out;
    };

    RW.registerMod("util:EntitySpawners", version);
    console.log("[EntitySpawners] " + version + " loaded — ctor hook armed at FUN_140" +
                SPAWNER_CTOR_RVA.toString(16) + ". Captures populate during chapter load.");
})();
