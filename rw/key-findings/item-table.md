# Item asset table (Magical Objects + Powerups)

**Status:** active reference. Source data extracted from the cooked Steam install (`DarkTalesResources/_Cooking/MzidisFqiidzyv/Oacqbiv/`, deciphered: `EntitySettings/Obzects/`) cross-checked against `tag=0x05` catalog records in clean save.
**Created:** 2026-04-29

The 114 magical-object catalog entries (in-run items + powerups) shipped in the current Ravenswatch build.

Two findings drive how this table is structured:

1. **Filename ≠ in-game display item.** Some effect files reuse another file's icon + display-name loc-key (e.g., `Avoid_Death_Once_Per_Chapter` displays as "Water of Life" because it shares Water of Life's icon and name key). Sort by **icon name** — that's the reliable display ID.
2. **Each item has two 16-byte GUIDs.** The catalog GUID appears once per save (in `tag=0x05` compendium records, identical across saves); the runtime GUID appears in `tag=0x1a` active-item records nested inside the run-state record (`tag=0x12`). Save-edit primitives use the runtime GUID. See `magical-objects.md` (TODO) for the active-item record format.

## Catalog summary

| Tier | Count |
|------|------:|
| Common | 13 |
| Rare | 12 |
| Epic | 11 |
| Legendary | 16 |
| Cursed | 16 |
| Powerups | 46 |
| **Total** | **114** |

## Verified aliases

| Display name | Icon | Effect file | Folder | Verification |
|---|---|---|---|---|
| Vorpal Blade | `Icon_Object_VorpalBlade` | `Kill_Low_Life_Enemies` | Legendary | original Save A slot at offset 0xef70 — display matched filename, +25 vitality observed (in run with HUD baseline 27) |
| Water of Life | `Icon_Object_UnspokenWater` | `Full_Heal_At_Day_Night` | Legendary | by-elimination only — `Avoid_Death_Once_Per_Chapter` (the deprecated Mortar) also displays as Water of Life via migration reroute (see Patch history). Lab-verify `Full_Heal_At_Day_Night` GUID `d6a8eb949785e4419016a9087b54a052` to promote |

The Cursed-folder effect `Destroy_Legendary_To_Damage` has icon `Icon_Object_BabaMortar` and is the post-patch Baba Yaga's Mortar — see "Patch history" below for why old saves carrying the legacy `Avoid_Death_Once_Per_Chapter` runtime GUID display as Water of Life.

## Catalog tables

Effect file = `Magical_Obzects!<Tier>!<Effect>.entity.ot.EntitySettingsResource.gen` (deciphered).
Icon = `Objects\<Icon>.png` referenced inside the entity file (most reliable display ID).
Name key = the `*_Name` localization key used to fetch the displayed item name.

Catalog GUID = the 16-byte ID in `tag=0x05` records (and the asset GUID embedded in the entity file body).
Runtime GUID = the 16-byte ID extracted via the `[u32 strlen=22]"Dt Magical Object Data"` anchor; it's what the engine reads from `tag=0x1a` active-item records.

### Common (13)

| Effect | Icon | Name key | Catalog GUID | Runtime GUID |
|---|---|---|---|---|
| Armor_Per_Obzect | _(none)_ | Armor_Per_Object | `6e67cf1c735f8a4994de0ce29e566b25` | `8aebaf5073029544905249e7b32d8c8d` |
| Damage_Per_Vitality | OgreBlood | Damage_Per_Vitality | `343e1f019286ed4889ff53ee3010faed` | `0bb75b45ea9bf74e978f2679279e153d` |
| Dash_Crit_Chance | EternalRose | Damage_Per_Debuff | `882cd038c5432741b0adc8ba3d3a9976` | `45535f5f42abca488de0cf93d3ac50dd` |
| Defense_To_Damage | _(none)_ | Defense_To_Damage | `c2abcdc57acb644e9b8b568fb3f8fa0d` | `26a8cbfceeff0b45bfa274a4c07f6f8a` |
| Gain_Shield_From_Orbs | GoldilocksPorridge | Damage_At_Full_Health | `37f3951cb69379408872847445e9283a` | `1825d8b4454ced4f85282ff186fab885` |
| Healing_Effect | MermaidTears | Healing_Effect | `800a5364fa975748ae9d341291c03fb1` | `e32da2e786dec64885600ffe2c1f8f24` |
| Increase_Damage_To_Boss | VoodooDoll | Damage_To_Boss | `567b1b987e8f944b85e6730e44533ceb` | `7062e5befc247a498b6998ee7d70b4cf` |
| Increase_Damage_To_Boss_And_Ignore_Resistance | VoodooDoll | Damage_To_Boss | `9044d0e85d320143bd5aae2b6fe74d60` | `ab17a5c4944b6245bf2c5abf9357ec03` |
| Orb_Grants_Strength | GoldilocksPorridge | Damage_At_Full_Health | `fecddcb2ac18474b9ed104ef38366cd7` | `0f43ddbf2741e548881b3a33f6c480f4` |
| Reduce_All_DS_Price | Dreamcatcher | Reduce_Price | `b537ee9fae74234ba8f93c4b99a806c5` | `a382ca9cc837ef4a867baa03b3a1e325` |
| Reduce_Dream_Shard_Price | Dreamcatcher | Reduce_Price | `2eaf32eba67e724f994190ab27589822` | `fc11ec3f4d247d45ad8a43bfa54dd8d1` |
| Reroll_To_Dream_Shards | _(none)_ | Reroll_To_Dreamshard | `0476423ecf286f4980833869e17c2251` | `7ef148a845771e498d544bdac4a53b87` |
| Spawn_Consumables | HornOfPlenty | Vitality_Per_Object | `8ce6f570f8b9374badb900cc770c57b2` | `80e8a676a33cf149a835315df87625ad` |

### Rare (12)

| Effect | Icon | Name key | Catalog GUID | Runtime GUID |
|---|---|---|---|---|
| AP_For_Dream_Shards_Stack | GoldenEgg | Dream_Shards_Stack_AP | `4c3f90cb8d981d4794e4d425d2f7b023` | `ae6896038d2a3544a25280d91a8c25e5` |
| Armour_Gain_Per_Missing_Health | DragonHide | Armour_Per_Health | `e38a950b57414b48a5303e20b7b6286c` | `a8a7edbaba5b9a4eb5db05c266f1403e` |
| Collection_To_Damage | _(none)_ | Collection_To_Damage | `52ed9bcb576a074ea86fa43414a6d1c7` | `524f330d6ffa7b4a9cd59b902a8b9388` |
| Damage_Attack | AceCard | Attack_Damage | `c6d2bc6dd466134fa3d1bd100c56794b` | `c8de1682dbc70349b45df89f77073dd5` |
| Damage_Power | KingCard | Power_Damage | `00e9da40959e80459b5fbaf5c593c490` | `6fc4cd8ef0a9e84a911b27375d9ddbe8` |
| Damage_Special | JackCard | Special_Damage | `920bdff949260842b30035b5e8514440` | `2e0c614f7b33c845a829eb2629378773` |
| Dash_Deal_Damage | Vajra | Dash_Deal_Damage | `52136ea9eb60444db15fefb72b9b68dc` | `261a393dfe4c5d43bf81cba2af85aa0e` |
| Gain_Armor_From_Talents_Rarity | DragonHide | Armour_Per_Health | `7685a1778716ea42923a906d80478ea1` | `119ecaa960eb454c966e01d6e4165969` |
| Gain_Passive_Heal | QueenCard | Defense_Regeneration | `687e86f635bd4c4e81636970ee1796dd` | `e47ba211bd56c44a9522b0057b32ae97` |
| Gain_Regeneration_On_Low_Life | UnicornHorn | Regeneration_On_Low_Life | `3bb9a725c9e3454486151e4317a613a9` | `7c7015b3221d034f94eb11032f3ba903` |
| Increase_Shield | FairyDust | Increase_Shield | `18df2de8bfe58a4895e266b4bca1de98` | `a87a5f06ddff894f8448d10a5d5b0231` |
| Passive_Heal | QueenCard | Defense_Regeneration | `e13c31a464d48549ad9238bcadbb5d26` | `764539167186ed47bf73a59d923b5ab6` |

### Epic (11)

| Effect | Icon | Name key | Catalog GUID | Runtime GUID |
|---|---|---|---|---|
| Copy_Card | JokerCard | Copy_Cards | `a44766b453f1ea4789c0627803c9fa2b` | `05e72793d95d6c4db1b5ce0ae54c9ccf` |
| Dash_Gain_Charge | CharmStone | Dash_Charge_Gain | `2ddc93f23fd55d4e832399c65dd04824` | `b3dd93e322c3234f945e80f57a5931f9` |
| Defensive_Gain_Charge | AdderStone | Defensive_Charge_Gain | `4340676515bbe84399833cfc5f57fef0` | `195806853d2dd943a0f9e366663f06dc` |
| Primary_Gain_Charge | FlamingPearl | Primary_Charge_Gain | `c308d9bc44e83e43a7c38d1dd38acbc4` | `1954d8bcf75030459201b0f94019f044` |
| Reduce_CD_And_Buff_Ultimate | RavenEye | Reduce_Ultimate_CD | `a020ed6649051741b73582198de0ad24` | `9a2c24abcf7e5f499f01f466b8a16c59` |
| Reduce_Dash_CD | RavenWing | Reduce_Dash_CD | `7593f0a9faed2847a4bfc79bf25681f5` | `10654b850150f2489e3d60c96e461fa6` |
| Reduce_Defensive_CD | RavenSkull | Reduce_Defense_CD | `82862138c33b0a4ab843cff71d6f8fe2` | `6ed916ec2ead1d4dbfecb8cd0d2b196a` |
| Reduce_Primary_CD | RavenClaw | Reduce_Power_CD | `f21c2ff89442db4ca9eaf8dd56b48e92` | `100e7eca17f3a543b0aaa727cca2304e` |
| Reduce_Secondary_CD | RavenBeak | Reduce_Special_CD | `22c17faf2cdc0f479d432d00d825553a` | `e87844f261b8834c95a40cb0bffc27cb` |
| Reduce_Ultimate_CD | RavenEye | Reduce_Ultimate_CD | `3dc17a71256494498d4c0575b2c7524f` | `8db2c6cad579894ab3223a80648fda9b` |
| Secondary_Gain_Charge | ThunderStone | Secondary_Charge_Gain | `f71ee3ec24419a4a90f2951356deed12` | `1d97edbd51d1934996a9cf79bca1a7ee` |

### Legendary (16)

| Effect | Icon | Name key | Catalog GUID | Runtime GUID |
|---|---|---|---|---|
| Abilities_Cooldown_Reduction_Per_Missing_Health | FatherTimeHourglass | Abilities_Cooldown_Reduction_Per_Missing_Health | `0808ec0c31f2584c8ae17e97921d09e1` | `c84ebfbeef7bfc49918e30fd77d48fbd` |
| All_Abilities_Gain_Charge | RavenEffigy | Ability_Charge | `bcf5a379399a68408b6905db2147b9b9` | `cb9a90bec8096342a32c801100456409` |
| Avoid_Death_Once_Per_Chapter | UnspokenWater | Fully_Health_Day_Night | `cae8330b21372b4aa449dbcb6579d709` | `1cc781a598b8314e9f52ae3c19d3edb3` |
| Clamp_High_Damage | GoldenCoatChainmail | Clamp_High_Damage | `a02e4b97d6ed9644886f3974f867cf94` | `5a4e27869c11aa4e94c6abaadc24e596` |
| Clear_Dash_Cooldown_On_Defense | FastWalkerBoots | Clear_Dash_Cooldown_On_Defense | `e3ea799cfb98964ba53c0139702c550e` | `40663bbf1035344cae216d94a1279543` |
| Damage_Per_Legendary_Skill | Excalibur | Damage_Per_Legendary_Object | `451566226f3f6a4abd259b5ef8c7dc9e` | `961f59f3b570f5468a9dab8ad7b3615f` |
| Dash_Apply_Vulnerable | RingOfDispel | Dash_Vulnerable | `2ca62b798fbe024895ea374de8a2c3cd` | `751263af0189b843abfa6f4e6408ff37` |
| Dash_Heal_For_Damage_Taken | SwanCloak | Dash_Heal_For_Damage_Taken | `2557249b1185884c9929606eb45c5758` | `b37898477ed664478b567385a87a5058` |
| Defense_Heal | HolyGrail | Defense_Heal_Nearby | `c41a0b1462c71845ba40f3d815629db2` | `dafb421140180a4e8884b390d63d99a9` |
| Extra_MO_Choice | Tamatebako | Extra_MO_Choice | `6586166c534a724eae1abcf6743ecb8e` | `f2e753c833519141ba07ef6c6ced6fc2` |
| Full_Heal_At_Day_Night | UnspokenWater | Fully_Health_Day_Night | `0dce777d898d3f4d8b6d0a868df5e08f` | `d6a8eb949785e4419016a9087b54a052` |
| Kill_Low_Life_Enemies | VorpalBlade | Kill_Low_Life_Enemies | `69fdfe207aaaac44b4d54daede4f074f` | `cf7d88d6e39d0e488d0efbec81723360` |
| Reduce_All_Abilities_CD | FatherTimeHourglass | Abilities_Cooldown_Reduction_Per_Missing_Health | `634529f4e9e829428404b073f61624e5` | `6f72772e6a162948ba9cb6003d03cdfb` |
| Ultimate_Gain_Charge | NibelungenRing | Ultimate_Charge_Gain | `5276758fefdb294ea0b2bba897da3bfb` | `e6a42a2d0a57124e89091ace191bfcd7` |
| Upgrade_All_Talents_Once | SolarCrown | _(none)_ | `032ec2fa8f467d4a994a8f46d57a4f2c` | `2d7a53e367237840a875ac9cff3f81dd` |
| Vitality_Per_Health_Globe | PhilosopherStone | Vitality_Per_Health_Globe | `58fa478432f4ec4ea7902b1e692e2da0` | `47db8829a3666e459b45aed07c03bdf2` |

### Cursed (16)

| Effect | Icon | Name key | Catalog GUID | Runtime GUID |
|---|---|---|---|---|
| Charge_To_Damage | _(none)_ | Charge_To_Damage | `6534d634a723c84ab9fa07071fa579bc` | `409b76ab14558c46bb75ce4e1dda5de6` |
| Convert_Vitality_Into_AP | BloodyMaryMirror | Armour_Into_Damage | `b0445ddc8fda37499067156cee0a08f6` | `9b9330629cf3824e9505b99fb4a41d0a` |
| Curse_Baba_Yaga_Revive | BabaMortar_Disabled | Curse_Baba_Yaga_Revive | `9fd28ede62d1d24c87043b3be91dcc15` | `ac7fe9ce5861474daa1e877aeff84dbb` |
| Curse_Increase_Power_Damage_And_Cooldown | NightmareThorn | Curse_Increase_Power_Damage_And_Cooldown | `697d4ce9f0b27b4cab152fc5f0acdbf4` | `0ee3457688ce694998377eb428f1b897` |
| Curse_Increase_Special_Damage_And_Cooldown | NightmareBoo | Curse_Increase_Special_Damage_And_Cooldown | `221b16d526acdd458e98b16cd0c3153a` | `fec9b2b87c78354eb9bb9ffcffc47c22` |
| Curse_Life_On_Hit | BlackLotus | Curse_Life_On_Hit | `bdb48389f19eec4a8ccafcdc2f80eaa0` | `8f27c45f0d0a714ea7ed58363affa0e1` |
| Curse_Lose_Life_Gain_Damage | MadHat | Lose_Dream_Shards_Instead_Of_Health | `9cda1cf5398b0340afe672868e05e2e3` | `6a78a088f3c2cc45b173115e15b9c4da` |
| Curse_Stack_Shard_Quest | _(none)_ | Stack_Shards | `4b88a8884f320045b1d3e527198ea2ec` | `60734f5d04b42d42af25a9c194fe3214` |
| Damage_Per_Cursed_Over_Legendary | OniMask | Damage_Per_Cursed_Over_Legendary | `1194e7a73bea2d4b876e71c3b266aba0` | `5067318fd0d19f4e894474bd3268fb57` |
| Dash_Intangible | WitchBroom | Dash_Intangible | `047b6c2219dcc2448df49aa304be9982` | `db75af84025c8f4fb7011fd480fe312f` |
| Destroy_Legendary_To_Damage | **BabaMortar** | Curse_Baba_Yaga_Revive | `e12554c452c67f4fa8d29f75185c7b7d` | `a2ec4039eb665d41a491b20077ce2f5c` |
| Double_Shard | HopeDiamond | Double_Shard | `7a0987018853664f852ef0e8b58bc624` | `d84f55cad16a3e4698083c49c52ed843` |
| Gain_Dream_Shards_On_Hit | MadHat | Lose_Dream_Shards_Instead_Of_Health | `2e2446e9efbf2445a980c419faabd097` | `d9e99e9e0a92d5419f264b9836839ec7` |
| Increase_Vitality_Reduce_Crit_Chance | Cauldron | Increase_Vitality_Reduce_Crit_Chance | `223637d792e9514697644e6128dc66b0` | `97f4dd3788635341ba2ff8d3b0afe1ef` |
| Move_Speed_Reduced_Armor | _(none)_ | Move_Speed | `6f6c6a5e5e65ad4f93840b340fd62e6b` | `cda02fa0abe35e439cbc4f46fda83899` |
| Temp_Dmg_Per_Health_Globe | _(none)_ | Ultimate_No_Cooldown | `94702dc221b41641a46a1c146c791b6f` | `945579ba3af1654b8ac14d19b2cdc408` |

### Powerups (46)

Powerup files mostly lack name keys / icons because they're "instant pickup" effects with embedded loc strings rather than equippable items.

| Effect | Icon | Name key | Catalog GUID | Runtime GUID |
|---|---|---|---|---|
| Power_Up_Armor | _(none)_ | Armour | `6efceaf0d17b51479a7edd4cfdcbdc85` | `a5b09a8600cc324c858f34534d76dfe3` |
| Power_Up_Astral_Relearn_Talents_High | _(none)_ | _(none)_ | `d1e83e3f2bbd1d4e920f584ef1d03d8f` | `9ebbbdba460a2b4188c236ec2b5a0ef4` |
| Power_Up_Astral_Relearn_Talents_Low | _(none)_ | _(none)_ | `d20dfad45fd1c043a6c5afc6d707dea2` | `f863d8390e3d554498a4e72de23f7a63` |
| Power_Up_Astral_Relearn_Talents_Medium | _(none)_ | _(none)_ | `1b88ff40c45cfe42bd363cc3cd2a0619` | `bb40c485a6c3104982a61714e115992b` |
| Power_Up_Astral_Reroll_High | _(none)_ | _(none)_ | `3bd230bdce33ea4880fa5fecf32a761e` | `9038bc6d6281f340a0f42f484fbd7d61` |
| Power_Up_Astral_Reroll_Low | _(none)_ | _(none)_ | `84f9972bbbee3e4e8dad02325e68be41` | `0bf487a1bad43f478c1575bcb5d5ef77` |
| Power_Up_Astral_Reroll_Medium | _(none)_ | _(none)_ | `4b928b59ae570e4580c4abf70fb5fdec` | `cee204c117b9484a9dfb3a4eecf4a4a0` |
| Power_Up_Astral_Upgrade_Talents_High | _(none)_ | _(none)_ | `24dbb0305d61c14196c8c67fc2f775d2` | `edb0b01c018b4c4c9ab857f47da5fac6` |
| Power_Up_Astral_Upgrade_Talents_Low | _(none)_ | _(none)_ | `0b0a649781227c4b9024bf66c5714aa3` | `1f0eb4be5fc89942962c489dde626e7b` |
| Power_Up_Astral_Upgrade_Talents_Medium | _(none)_ | _(none)_ | `fd5fbde7fb090a45b0712440fff372a9` | `9e804da930916049b296bbacc1e84aa4` |
| Power_Up_Critical_Chance | _(none)_ | Chance | `f0f6e1e5a380ec44b2a41aacba21fd73` | `4c96d6bacc63a343aa54c60b8c2e33d5` |
| Power_Up_Critical_Damage | _(none)_ | Crit_Damage | `7d32b206a29d66468f23f753a9f1a9e2` | `808559072a5d1c4f8a9f514f798b438b` |
| Power_Up_Damage | _(none)_ | Increase_Damage | `b3f0836da5e72242b64dfa837a535e33` | `5fad4a9e50377040ab97eec60598742e` |
| Power_Up_Grimoire_Armor_High | _(none)_ | _(none)_ | `8cc0bdbf49def04d94f43b216b3d8ad2` | `c947a78006fcaa478d8d2f8327f5962e` |
| Power_Up_Grimoire_Armor_Low | _(none)_ | _(none)_ | `15d849f81a48224abe5bf98df8ccf74e` | `0e7c948b7e44304f94969a6824d0c94e` |
| Power_Up_Grimoire_Armor_Medium | _(none)_ | _(none)_ | `3c310f231a63d442bf5411d919cc0024` | `ac8d1d1b4adf054593b74ab2f784419b` |
| Power_Up_Grimoire_Crit_Chance_High | _(none)_ | _(none)_ | `174b205ec0d28845b38dbc233048bc0f` | `f60a2c58fc915244ba50a771be81a4ac` |
| Power_Up_Grimoire_Crit_Chance_Low | _(none)_ | _(none)_ | `4ae7e480a018284d925d4ed3a4be29a9` | `cb24d1a706455847bdf98e2913d9d195` |
| Power_Up_Grimoire_Crit_Chance_Medium | _(none)_ | _(none)_ | `29e534939deb6e4a9609a0284db857e0` | `7583cefd9a787d498a0cb87670deadeb` |
| Power_Up_Grimoire_Crit_Damage_High | _(none)_ | _(none)_ | `ddf053d6a5c95f4e8cdcb147a57971bc` | `f2f629c2dfe4ee41986ab29fad100137` |
| Power_Up_Grimoire_Crit_Damage_Low | _(none)_ | _(none)_ | `1eaf0fb22dc86b4ea069ac4ddea00946` | `985e04d5cac82d4b87950536e75b38a2` |
| Power_Up_Grimoire_Crit_Damage_Medium | _(none)_ | _(none)_ | `032aa6da13a850498e8ad8d3352d1793` | `b77e08bc8f30cb4eab3e153bc4a9bf5e` |
| Power_Up_Grimoire_Damage_High | _(none)_ | _(none)_ | `caea709443b8aa4e9b72efef98758dfb` | `0bfd860d5ba5ab4f9c39fe87f1cef10a` |
| Power_Up_Grimoire_Damage_Low | _(none)_ | _(none)_ | `79a8178b6d0f724e9f51409ae71714ba` | `1df5bb60a12cd64699ea36dd01ee4d1d` |
| Power_Up_Grimoire_Damage_Medium | _(none)_ | _(none)_ | `ec613b46f2491f469f95bf492b0e0072` | `d740c75e23e4ce4491bc0c55bfc6920d` |
| Power_Up_Grimoire_Dream_Shard_High | _(none)_ | _(none)_ | `af5ca41f453fdb4d8d086e78b1200729` | `96d87509f866b846a155409ac11bf2d3` |
| Power_Up_Grimoire_Dream_Shard_Low | _(none)_ | _(none)_ | `4f13e6c567b4bf4899376a444d4317a1` | `bf42e87827819940a3b5c1a434db8c3a` |
| Power_Up_Grimoire_Dream_Shard_Medium | _(none)_ | _(none)_ | `c4df5c00b452274889102cf6729bfa12` | `761b1b60cbbdc941a28ae35c8371db25` |
| Power_Up_Grimoire_Reroll_High | _(none)_ | _(none)_ | `a1853ba9db160d4ebe224a1bdc1ea841` | `bb0a5145795d1744bb336c4e6626121e` |
| Power_Up_Grimoire_Reroll_Low | _(none)_ | _(none)_ | `5b7cdcd9659ba64a86b728cae889951d` | `df4b5545a8173643a8b59497dfdaafa4` |
| Power_Up_Grimoire_Reroll_Medium | _(none)_ | _(none)_ | `3d31f550aa75db4eacc9f2e5cc485bcc` | `0a9690b3fabedf45a6a7370ef6381928` |
| Power_Up_Grimoire_Vitality_High | _(none)_ | _(none)_ | `ad2a3f793647f447a0adcb973c450d6c` | `e4216a998446e045be775748bad7fe7c` |
| Power_Up_Grimoire_Vitality_Low | _(none)_ | _(none)_ | `f2524f8f800f4849b106581382223e04` | `9a87a144ba0bd0419190bb9de43592a2` |
| Power_Up_Grimoire_Vitality_Medium | _(none)_ | _(none)_ | `0d7b1ae730f2154990ce795ca8a85756` | `ae655c5b934f844ab6b39874efb294c9` |
| Power_Up_Heal | _(none)_ | Heal | `0390abf5913af043bf9f19ece42954ef` | `cd00f8bf584ede4684a3f8f8fc74101d` |
| Power_Up_Sandman_Mazor_Duplicate_Epic_Obzect | _(none)_ | Sandman_DuplicateEpicObject | `d7164050c7837c41ae0c28d13ff5827a` | `9d12f8cb97bb9f4498df58e993487163` |
| Power_Up_Sandman_Mazor_Upgrade_Talent_To_Legendary | _(none)_ | Sandman_UpgradeTalentToLegendary | `1619441568f7504486a4cb0af0f98eaa` | `8507cb019489964b9122d62b662124a2` |
| Power_Up_Sandman_Medium_Duplicate_Common_Obzect | _(none)_ | Sandman_DuplicateCommonObject2 | `8040928bcd741d4b89b12c55bb3f8fc7` | `b8576af53db52244aae1c06d6938742f` |
| Power_Up_Sandman_Medium_Duplicate_Obzect | _(none)_ | Sandman_DuplicateObject | `8f1e4cb4983cda4587e535a610ff6b83` | `0cf9b4a2161cc34a952b761f23d80899` |
| Power_Up_Sandman_Medium_Duplicate_Rare_Obzect | _(none)_ | Sandman_DuplicateRareObject | `60383aed84f3aa478757948fadf25449` | `e300d39659e62449a9108afc3b4bcb2a` |
| Power_Up_Sandman_Medium_Upgrade_2_Talent | _(none)_ | Sandman_Upgrade2Talent | `81e932de6aaf794282e59fb0ed622c91` | `c0ece9844a4c244893abb68b9aa62880` |
| Power_Up_Sandman_Minor_Heal | _(none)_ | Sandman_Heal | `2f786c03b2a4414aa8d3d5c2a0405f9e` | `7ba27e8cc8bef84c882b3ed2e4fb62f0` |
| Power_Up_Sandman_Minor_Reroll | _(none)_ | Sandman_Reroll | `642e4da7b99b6e48999ebe643400d9aa` | `b9f8ef4c30e84f48b6ebc583da0a1191` |
| Power_Up_Sandman_Minor_Shield | _(none)_ | Sandman_Shield | `def289a2924963439a4d4a23e3243d46` | `ecf2c3a488651a4cafd1f79eb6d97401` |
| Power_Up_Sandman_Minor_Strength | _(none)_ | Sandman_Strength | `327271e9dc17684383da51a1f7bf166d` | `3ddade2c29d3dc4dbf681379a6e93bb4` |
| Power_Up_Vitality | _(none)_ | Increase_Vitality | `519dd0325fd71d4c839c70f1ffad52f9` | `cc7ed5d4e4dedd43bbf65a114f4626d4` |

## Display-name duplicates

Filename can mislead — these effect-file pairs share the same icon and name key, so they display as the same in-game item:

| Icon | Name key | Effect files |
|---|---|---|
| `Icon_Object_UnspokenWater` | `Fully_Health_Day_Night` | `Avoid_Death_Once_Per_Chapter` (Legendary), `Full_Heal_At_Day_Night` (Legendary) |
| `Icon_Object_VoodooDoll` | `Damage_To_Boss` | `Increase_Damage_To_Boss` (Common), `Increase_Damage_To_Boss_And_Ignore_Resistance` (Common) |
| `Icon_Object_GoldilocksPorridge` | `Damage_At_Full_Health` | `Gain_Shield_From_Orbs` (Common), `Orb_Grants_Strength` (Common) |
| `Icon_Object_Dreamcatcher` | `Reduce_Price` | `Reduce_All_DS_Price` (Common), `Reduce_Dream_Shard_Price` (Common) |
| `Icon_Object_DragonHide` | `Armour_Per_Health` | `Armour_Gain_Per_Missing_Health` (Rare), `Gain_Armor_From_Talents_Rarity` (Rare) |
| `Icon_Object_QueenCard` | `Defense_Regeneration` | `Gain_Passive_Heal` (Rare), `Passive_Heal` (Rare) |
| `Icon_Object_RavenEye` | `Reduce_Ultimate_CD` | `Reduce_CD_And_Buff_Ultimate` (Epic), `Reduce_Ultimate_CD` (Epic) |
| `Icon_Object_FatherTimeHourglass` | `Abilities_Cooldown_Reduction_Per_Missing_Health` | `Abilities_Cooldown_Reduction_Per_Missing_Health` (Legendary), `Reduce_All_Abilities_CD` (Legendary) |
| `Icon_Object_BabaMortar` (and `_Disabled` variant) | `Curse_Baba_Yaga_Revive` | `Destroy_Legendary_To_Damage` (Cursed), `Curse_Baba_Yaga_Revive` (Cursed) |
| `Icon_Object_MadHat` | `Lose_Dream_Shards_Instead_Of_Health` | `Curse_Lose_Life_Gain_Damage` (Cursed), `Gain_Dream_Shards_On_Hit` (Cursed) |

These pairs likely represent paired upgrade variants of the same item (e.g., `Increase_Damage_To_Boss` is the base form and `_And_Ignore_Resistance` is the upgraded variant from a `Power_Up_Astral_Upgrade_Talents` interaction). The engine still distinguishes them by runtime GUID for state tracking.

## Patch history — Baba Yaga's Mortar rework

A pre-patch and post-patch Mortar coexist in the catalog. Both are Cursed-themed but tier and display reflect a backward-compat migration:

| | Pre-patch Mortar | Post-patch Mortar |
|---|---|---|
| In-game effect | Avoid death once per chapter | Destroy legendary items; +50 damage per legendary destroyed |
| Effect file | `Magical_Obzects!Legendary!Avoid_Death_Once_Per_Chapter` | `Magical_Obzects!Cursed!Destroy_Legendary_To_Damage` |
| Tier of file | Legendary (legacy) | Cursed (current) |
| Icon | `Icon_Object_UnspokenWater` (rerouted to Water of Life) | `Icon_Object_BabaMortar` |
| Name key | `Fully_Health_Day_Night_Name` (rerouted to Water of Life) | `Curse_Baba_Yaga_Revive_Name` |
| Inheritance | references `Full_Heal_At_Day_Night.entity.ot` | _(no override)_ |
| Runtime GUID | `1cc781a598b8314e9f52ae3c19d3edb3` | `a2ec4039eb665d41a491b20077ce2f5c` |

**Migration mechanism:** the old Mortar entity (`Avoid_Death_Once_Per_Chapter.entity.ot.gen`) was kept in the 114-item catalog so old saves carrying its catalog-GUID don't break. Its display data (name + icon) was rerouted to inherit from `Full_Heal_At_Day_Night.entity.ot.gen` (Water of Life). Any save record with the old Mortar's runtime GUID `1cc781a598b8314e9f52ae3c19d3edb3` now displays as Water of Life. **This is what produced the apparent mismatch in the 2026-04-28 lab swap** — we wrote the OLD Mortar's runtime GUID and the engine displayed Water of Life because of the rerouted inheritance.

Lesson: file names trace dev-internal effect classes and freeze at creation time; gameplay rebalances reroute display via name-key + icon inheritance, not by renaming the file. **Always derive display identity from icon + name key, never from filename alone.**

The pairing `Curse_Baba_Yaga_Revive` (icon `BabaMortar_Disabled`) is likely the visual state of the post-patch Mortar after it has consumed a legendary and is on cooldown, or possibly an additional related variant.

## Extraction methodology

For each entity-settings file under `EntitySettings/Obzects/Magical_Obzects!*`:

1. **Filename effect identifier** — decipher the cooked filename via `tools/rerw-src/lib/cipher.decipher`, parse `Magical_Obzects!<Tier>!<Effect>.entity.ot.EntitySettingsResource.gen`.

2. **Catalog GUID** — every catalog GUID from clean save's `tag=0x05` records appears exactly once in the body of one entity file. 1:1 mapping.

3. **Runtime GUID** — extract the 16 bytes immediately preceding the anchor `[u32 strlen=22]"Dt Magical Object Data"` (full string `Dt Magical Object Data` with spaces). Each file has exactly one anchor match. Verified via 5 independent save-occurrence sanity checks.

4. **Icon** — regex match `Objects\\(Icon_Object_[A-Za-z0-9_]+)\.png` in body.

5. **Name key** — first match of `[A-Za-z][A-Za-z0-9_]+_Name` in body.

Eleven `_Model` template files (Powerup_Astral_*, Powerup_Grimoire_*) lack the `Dt Magical Object Data` anchor and are excluded — they're skeleton/inheritance roots, not catalog entries.

## Sources

- `/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking/MzidisFqiidzyv/Oacqbiv/` — cooked entity files (deciphered: `EntitySettings/Obzects/`).
- `rw/harvested/EntitySettings/Obzects/` — local read-only copy (gitignored).
- `rw/saves/proofs/geppetto/clean/Profile_1.ob` — source of `tag=0x05` catalog GUIDs.
- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — Save A, source of original Vorpal Blade slot for verification.
- `rw/saves/edits/lab/geppetto/laser-lenses_1/item-vorpal-blade-to-baba-yagas-mortar/Profile_1.ob` — lab swap that inadvertently confirmed `Avoid_Death_Once_Per_Chapter` displays as Water of Life.
- Extraction script: `rw/dumps/items_build_table.py` (gitignored).
