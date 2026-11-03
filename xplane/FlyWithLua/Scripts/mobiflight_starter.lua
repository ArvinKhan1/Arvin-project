-- MobiFlight starter helper for X-Plane 11 (FlyWithLua NG)
--
-- X-Plane starters only crank while their command is held, but MobiFlight 9.7
-- can only fire a command once. MobiFlight writes the dataref below instead:
--   mobiflight/starter = bit mask of engines to crank (1 = engine 1, 2 = engine 2,
--   4 = engine 3, 8 = engine 4, 15 = all, 0 = release)
-- and this script holds sim/starters/engage_starter_N while the bit is set.

define_shared_DataRef("mobiflight/starter", "Int")
dataref("mf_starter", "mobiflight/starter", "writable")

local MAX_ENGINES = 4
local mf_starter_held = 0

function mf_starter_update()
    local wanted = mf_starter
    if wanted == mf_starter_held then return end
    for i = 1, MAX_ENGINES do
        local bit = 2 ^ (i - 1)
        local want_on = math.floor(wanted / bit) % 2 == 1
        local is_on = math.floor(mf_starter_held / bit) % 2 == 1
        if want_on and not is_on then
            command_begin("sim/starters/engage_starter_" .. i)
        elseif is_on and not want_on then
            command_end("sim/starters/engage_starter_" .. i)
        end
    end
    mf_starter_held = wanted
end

do_every_frame("mf_starter_update()")
