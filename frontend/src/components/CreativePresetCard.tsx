'use client';

import type { CSSProperties } from 'react';
import { ArrowUpRight, Check, Layers3, Palette, Sparkles } from 'lucide-react';
import type { StudioCatalog } from '@/lib/api';

type TemplatePreset = StudioCatalog['templates'][number];
type StylePreset = StudioCatalog['styles'][number];
export type CreativePreset = TemplatePreset | StylePreset;
export type CreativePresetKind = 'template' | 'style';

export function presetKind(preset: CreativePreset): CreativePresetKind {
  return 'beats' in preset ? 'template' : 'style';
}

export function PresetArtwork({
  preset,
  kind = presetKind(preset),
  compact = false,
}: {
  preset: CreativePreset;
  kind?: CreativePresetKind;
  compact?: boolean;
}) {
  const colors = 'colors' in preset ? preset.colors : ['#14213D', '#FCA311', '#E5E5E5'];
  const swatch = colors.slice(0, 4);
  const id = preset.id.replace(/^favorite:(template|style):/, '');
  const artClasses = 'h-full w-full';

  if (preset.custom && preset.image) {
    return <img src={preset.image} alt="" className={`w-full object-cover ${artClasses}`} />;
  }

  if (kind === 'style') {
    if (id === 'swiss') {
      return (
        <div className={`relative overflow-hidden bg-[#f4f2ec] p-5 text-[#111] ${artClasses}`}>
          <div className="absolute right-[13%] top-[16%] h-[43%] aspect-square rounded-full bg-[#e00024]" />
          <div className="absolute left-[7%] top-[8%] font-mono text-[9px] leading-tight">INFORMATION<br />DESIGN / 2026</div>
          <div className={`absolute bottom-[8%] left-[7%] ${compact ? 'text-[46px]' : 'text-[72px]'} font-black leading-[0.84]`}>Swiss<br />Grid</div>
          <div className="absolute bottom-[8%] right-[8%] h-[31%] w-[2px] bg-[#111]" />
        </div>
      );
    }
    if (id === 'bauhaus') {
      return (
        <div className={`relative overflow-hidden bg-[#f1ecdf] ${artClasses}`}>
          <div className="absolute left-[8%] top-[10%] h-[52%] aspect-square rounded-full bg-[#d72632]" />
          <div className="absolute right-[8%] top-[14%] h-[38%] w-[31%] bg-[#1e43bd]" />
          <div className="absolute bottom-[8%] left-[12%] h-[21%] w-[63%] bg-[#171717]" />
          <span className="absolute bottom-[14%] left-[15%] text-[11px] font-black text-white">FORM / FUNCTION</span>
          <div className="absolute left-[52%] top-[22%] h-[44%] w-[3px] rotate-[24deg] bg-[#171717]" />
        </div>
      );
    }
    if (id === 'constructivism') {
      return (
        <div className={`relative overflow-hidden bg-[#171717] ${artClasses}`}>
          <div className="absolute -left-[4%] top-[18%] h-[76%] w-[43%] -rotate-[24deg] bg-[#cf2636]" />
          <div className="absolute left-[36%] top-[-24%] h-[145%] w-[8%] -rotate-[24deg] bg-[#eee9dd]" />
          <div className={`absolute bottom-[11%] right-[7%] max-w-[58%] text-right ${compact ? 'text-[32px]' : 'text-[51px]'} font-black uppercase leading-[0.9] text-[#f5f1e7]`}>Move<br />Forward</div>
          <span className="absolute right-[8%] top-[9%] font-mono text-[10px] text-[#eee9dd]">POSTER 04 / 1924</span>
        </div>
      );
    }
    if (id === 'brutalism') {
      return (
        <div className={`relative overflow-hidden border-[9px] border-[#171717] bg-[#e5ff00] p-4 text-[#171717] ${artClasses}`}>
          <div className="font-mono text-[9px]">RAW SIGNAL / 001</div>
          <div className={`mt-[8%] ${compact ? 'text-[47px]' : 'text-[74px]'} font-black uppercase leading-[0.84]`}>LOUD<br />IDEAS</div>
          <div className="absolute bottom-[9%] right-[8%] h-12 w-12 rotate-12 border-[5px] border-[#171717]" />
          <div className="absolute bottom-[12%] left-[8%] w-[42%] border-t-[5px] border-[#171717]" />
        </div>
      );
    }
    if (id === 'realism') {
      return (
        <div className={`relative overflow-hidden bg-[#d9dfd7] ${artClasses}`}>
          <div className="absolute inset-x-0 bottom-0 h-[24%] bg-[#81735f]" />
          <div className="absolute inset-y-[10%] left-[7%] w-[38%] border-[5px] border-[#526358] bg-[linear-gradient(120deg,#d8e4dd_0%,#e4d6bd_48%,#78907c_49%,#94a591_100%)] shadow-[inset_-8px_0_18px_rgba(40,50,40,.25)]">
            <div className="absolute bottom-0 left-[8%] h-[47%] w-[25%] bg-[#687667]" />
            <div className="absolute bottom-0 right-[12%] h-[35%] w-[30%] rounded-t-[50%] bg-[#c4aa83]" />
          </div>
          <div className="absolute bottom-[18%] left-[57%] h-[47%] w-[3px] bg-[#536257]" />
          <div className="absolute bottom-[18%] left-[54%] h-[33%] w-[13%] rounded-t-[45%] bg-[#43534a]" />
          <div className="absolute bottom-[55%] left-[57%] h-[15%] w-[7%] rounded-full bg-[#c4aa83]" />
          <div className="absolute right-[7%] top-[10%] font-mono text-[9px] text-[#344438]">35MM / NATURAL LIGHT</div>
          <span className={`absolute bottom-[8%] right-[8%] ${compact ? 'text-[18px]' : 'text-[26px]'} font-serif text-white/90`}>生活的光</span>
        </div>
      );
    }
    if (id === 'deconstruction') {
      return (
        <div className={`relative overflow-hidden bg-[#f5f5f2] ${artClasses}`}>
          <div className="absolute left-[25%] top-[5%] h-[85%] w-[36%] -rotate-12 bg-[#0b735e]" />
          <div className="absolute left-[8%] top-[26%] h-[42%] w-[84%] rotate-[9deg] border-y-[3px] border-[#121212] bg-[#f5f5f2]" />
          <span className={`absolute left-[8%] top-[33%] rotate-[9deg] ${compact ? 'text-[33px]' : 'text-[56px]'} font-black leading-none text-[#161616]`}>RE:FRAME</span>
          <span className="absolute bottom-[7%] right-[7%] font-mono text-[9px] text-[#161616]">TYPE / COLLAGE / 03</span>
          <div className="absolute right-[18%] top-[7%] h-[80%] w-px rotate-[18deg] bg-[#121212]" />
        </div>
      );
    }
    if (id === 'neo_expressionism') {
      return (
        <div className={`relative overflow-hidden bg-[#e9ccb0] ${artClasses}`}>
          <div className="absolute -left-[10%] top-[32%] h-[25%] w-[85%] -rotate-12 bg-[#b52844]" />
          <div className="absolute left-[35%] top-[-20%] h-[150%] w-[25%] rotate-[17deg] bg-[#285e58]" />
          <div className="absolute left-[24%] top-[13%] h-[63%] w-[42%] rotate-[-9deg] rounded-[25%_40%_15%_30%] border-[6px] border-[#25242a] bg-[#edbd46]" />
          <div className="absolute left-[32%] top-[36%] h-[11%] w-[10%] -rotate-12 border-t-[5px] border-[#25242a]" />
          <div className="absolute left-[48%] top-[33%] h-[11%] w-[10%] rotate-12 border-t-[5px] border-[#25242a]" />
          <div className="absolute left-[39%] top-[52%] h-[10%] w-[19%] rotate-6 bg-[#b52844]" />
          <div className="absolute inset-0 opacity-25 mix-blend-multiply bg-[repeating-linear-gradient(105deg,transparent_0_5px,#735440_5px_6px)]" />
          <div className={`absolute bottom-[5%] left-[6%] ${compact ? 'text-[22px]' : 'text-[38px]'} font-serif font-black text-[#181818]`}>RAW EMOTION</div>
        </div>
      );
    }
    return (
      <div className="relative grid h-full grid-cols-6 grid-rows-4 gap-2 overflow-hidden bg-[#f2f1ed] p-4">
        {swatch.map((color, index) => (
          <div
            key={`${color}-${index}`}
            className={`${index === 0 ? 'col-span-3 row-span-3 rounded-full' : index === 1 ? 'col-span-3 row-span-2' : 'col-span-2 row-span-2'} ${index % 2 ? 'rounded-sm' : 'rounded-[45%]'}`}
            style={{ background: color }}
          />
        ))}
        <span className="absolute bottom-3 left-4 font-mono text-[10px] font-bold text-[#263040]">{preset.name.toUpperCase()}</span>
      </div>
    );
  }

  const beats = 'beats' in preset ? preset.beats.slice(0, 3) : [];
  if (id === 'product_reveal') {
    return (
      <div className={`relative overflow-hidden bg-[#ece9e2] ${artClasses}`}>
        <div className="absolute left-[9%] top-[16%] font-mono text-[9px] text-[#555]">NEED / SOLUTION / USE</div>
        <div className="absolute bottom-[12%] left-[8%] h-[56%] w-[21%] rounded-sm bg-[#b9b8b1]" />
        <div className="absolute bottom-[12%] left-[39%] h-[68%] w-[25%] rounded-[18%] border-[3px] border-[#222] bg-[#d8d7d1] shadow-[10px_10px_0_#b5b2a9]">
          <div className="mx-auto mt-[16%] h-[44%] w-[72%] rounded-[14%] border border-[#888]" />
          <div className="mx-auto mt-[10%] h-2 w-2 rounded-full bg-[#222]" />
        </div>
        <div className="absolute bottom-[12%] right-[8%] w-[20%] border-b-2 border-[#222]" />
        <div className="absolute right-[12%] top-[24%] text-right font-mono text-[9px] leading-5 text-[#555]">01<br />02<br />03</div>
      </div>
    );
  }
  if (id === 'visual_essay') {
    return (
      <div className={`relative overflow-hidden bg-[#f4f1e9] p-4 text-[#17253a] ${artClasses}`}>
        <div className="flex items-center justify-between border-b border-[#17253a]/30 pb-2 font-mono text-[9px]"><span>FIELD NOTES / 07</span><span>OBSERVE → TEST</span></div>
        <div className="mt-[7%] grid grid-cols-[1fr_1.1fr] gap-3">
          <div className="space-y-2"><div className="h-3 w-4/5 bg-[#17253a]" /><div className="h-2 w-full bg-[#9aa1a3]" /><div className="h-2 w-5/6 bg-[#9aa1a3]" /><div className="mt-3 border-l-2 border-[#b64139] pl-2 font-serif text-[11px] leading-4">一个现象，两个解释。</div></div>
          <div className="relative h-[82px] border-b border-l border-[#17253a]/40"><div className="absolute bottom-0 left-[10%] h-[35%] w-[15%] bg-[#b64139]" /><div className="absolute bottom-0 left-[34%] h-[58%] w-[15%] bg-[#3e6681]" /><div className="absolute bottom-0 left-[58%] h-[74%] w-[15%] bg-[#789080]" /><div className="absolute bottom-0 left-[82%] h-[47%] w-[12%] bg-[#d2aa58]" /></div>
        </div>
        <div className="absolute bottom-[7%] left-[7%] font-mono text-[9px]">CLAIM / EVIDENCE / CONTRAST</div>
      </div>
    );
  }
  if (id === 'lyric_journey') {
    return (
      <div className={`relative overflow-hidden bg-[#171c2c] p-4 text-white ${artClasses}`}>
        <div className="absolute inset-x-0 top-[30%] h-[42%] bg-[linear-gradient(180deg,transparent,#395077,transparent)]" />
        <div className="absolute left-[14%] top-[19%] h-[62%] w-[2px] bg-[#e59b77]" />
        <div className="absolute left-[14%] top-[20%] h-2 w-2 -translate-x-[3px] rounded-full bg-[#e59b77]" />
        <div className="absolute left-[21%] top-[20%] font-mono text-[9px] text-white/60">VERSE 01</div>
        <div className="absolute left-[21%] top-[32%] font-serif text-[clamp(22px,3vw,39px)] leading-none">潮汐退去以后</div>
        <div className="absolute left-[21%] top-[48%] font-serif text-[clamp(22px,3vw,39px)] leading-none text-[#e9a17c]">仍听见你的名字</div>
        <div className="absolute bottom-[13%] left-[21%] flex h-5 items-end gap-1">{[5, 12, 8, 19, 13, 24, 9, 16, 6, 20, 12, 25, 9, 16, 6, 18, 10, 22].map((height, index) => <i key={index} className="block w-[3px] bg-[#d8a285]/80" style={{ height }} />)}</div>
        <div className="absolute bottom-[8%] right-[9%] font-mono text-[9px]">00:42 / LRC</div>
      </div>
    );
  }
  if (id === 'beat_geometry') {
    return (
      <div className={`relative overflow-hidden bg-[#101820] ${artClasses}`}>
        <div className="absolute inset-0 opacity-35 bg-[linear-gradient(90deg,transparent_49%,#e4b94e_50%,transparent_51%),linear-gradient(transparent_49%,#e4b94e_50%,transparent_51%)] bg-[length:42px_42px]" />
        <div className="absolute left-[12%] top-[18%] h-[48%] aspect-square rounded-full border-[10px] border-[#e4b94e]" />
        <div className="absolute right-[13%] top-[17%] h-[50%] w-[28%] rotate-45 border-[8px] border-[#4db5a5]" />
        <div className="absolute left-[8%] top-[73%] h-[2px] w-[84%] bg-white/30" />
        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((item, index) => <span key={item} className="absolute bottom-[14%] block w-[4%] bg-[#da5260]" style={{ height: `${16 + (index % 4) * 11}px`, left: `${10 + index * 7}%` }} />)}
        <span className="absolute left-[8%] top-[7%] font-mono text-[9px] text-white/70">KICK / SNARE / DROP</span>
      </div>
    );
  }
  if (id === 'explainer') {
    return (
      <div className={`relative overflow-hidden bg-[#f1eee7] p-4 text-[#232b31] ${artClasses}`}>
        <div className="flex justify-between border-b-2 border-[#232b31] pb-2 font-mono text-[9px]"><span>THE EXPLAINER</span><span>01 / 06</span></div>
        <div className={`mt-[7%] font-serif font-black leading-[0.88] ${compact ? 'text-[37px]' : 'text-[57px]'}`}>A GOOD<br />QUESTION</div>
        <div className="mt-3 grid grid-cols-3 gap-2 font-mono text-[9px]"><span className="border-t border-[#b74b3e] pt-1">01 CONTEXT</span><span className="border-t border-[#3c6780] pt-1">02 EVIDENCE</span><span className="border-t border-[#798664] pt-1">03 ACTION</span></div>
      </div>
    );
  }
  if (id === 'personal_essay') {
    return (
      <div className={`relative overflow-hidden bg-[#d9d3c6] p-5 ${artClasses}`}>
        <div className="absolute inset-y-[9%] left-[12%] right-[12%] border border-[#b7ad9c] bg-[#f3eee4] p-[7%] shadow-[8px_9px_0_rgba(43,45,42,.13)]">
          <div className="font-mono text-[9px] tracking-[0.18em] text-[#777064]">A NOTE FROM THE AUTHOR</div>
          <div className={`mt-[9%] font-serif ${compact ? 'text-[24px]' : 'text-[38px]'} leading-[1.05] text-[#2b3332]`}>那天我第一次<br />改了主意。</div>
          <div className="mt-[8%] space-y-1.5">{[0, 1, 2].map((line) => <div key={line} className="h-px bg-[#aaa292]" />)}</div>
          <div className="absolute bottom-[7%] right-[8%] font-mono text-[9px] text-[#777064]">SCENE / VIEW / REVISIT</div>
        </div>
      </div>
    );
  }
  return (
    <div className={`grid grid-cols-3 gap-2 overflow-hidden bg-[#121a28] p-4 ${artClasses}`}>
      {beats.map((beat, index) => (
        <div key={`${index}-${beat}`} className="relative flex flex-col justify-between overflow-hidden rounded-sm border border-white/15 bg-[#26364c] p-2.5 text-white">
          <div className={`absolute inset-0 opacity-60 ${index === 0 ? 'bg-[linear-gradient(145deg,#101820_0%,#507f9d_52%,#e0b26d_100%)]' : index === 1 ? 'bg-[linear-gradient(135deg,#201b35_0%,#b34361_58%,#e4b889_100%)]' : 'bg-[linear-gradient(135deg,#102d35_0%,#529589_50%,#d2b36f_100%)]'}`} />
          <span className="relative font-mono text-[9px] text-white/65">SCENE 0{index + 1}</span>
          <span className="relative line-clamp-3 text-xs font-black leading-tight">{beat}</span>
          <span className="relative h-[2px] w-8 bg-white/75" />
        </div>
      ))}
    </div>
  );
}

export function CreativePresetCard({
  preset,
  selected = false,
  onClick,
  compact = false,
}: {
  preset: CreativePreset;
  selected?: boolean;
  onClick: () => void;
  compact?: boolean;
}) {
  const kind = presetKind(preset);
  const custom = preset.custom;
  const colors = 'colors' in preset ? preset.colors : [];
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`group min-w-0 overflow-hidden rounded-sm border bg-white text-left transition ${selected ? 'border-primary ring-2 ring-primary/20' : 'border-gray-200 hover:-translate-y-0.5 hover:border-gray-400 hover:shadow-md'}`}
    >
      <div className="relative aspect-[1.52] overflow-hidden">
        <PresetArtwork preset={preset} kind={kind} compact />
        <span className="absolute left-2.5 top-2.5 rounded-full bg-white/90 px-2 py-1 text-[10px] font-bold text-gray-700">
          {preset.category || (kind === 'style' ? '视觉风格' : '内容模板')}
        </span>
        {selected && <span className="absolute right-2.5 top-2.5 grid h-6 w-6 place-items-center rounded-full bg-primary text-white"><Check size={14} /></span>}
        {custom && <span className="absolute bottom-2.5 right-2.5 rounded-sm bg-black/70 px-2 py-1 text-[10px] font-bold text-white">自定义</span>}
      </div>
      <div className={compact ? 'p-3' : 'p-4'}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-black text-gray-900">{preset.name}</div>
            <div className="mt-1 line-clamp-2 min-h-9 text-[11px] leading-4 text-gray-500">{preset.description}</div>
          </div>
          <ArrowUpRight size={14} className="mt-0.5 shrink-0 text-gray-400 transition group-hover:text-primary" />
        </div>
        <div className="mt-2.5 flex min-h-5 items-center gap-1.5">
          {kind === 'style' ? (
            colors.slice(0, 5).map((color, index) => <span key={`${color}-${index}`} className="h-3.5 w-3.5 rounded-full border border-black/10" style={{ background: color } as CSSProperties} />)
          ) : (
            <>
              <Layers3 size={12} className="text-gray-400" />
              <span className="truncate text-[10px] text-gray-500">{'beats' in preset ? preset.beats.slice(0, 2).join(' · ') : ''}</span>
            </>
          )}
          <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] font-bold text-gray-400">
            {kind === 'style' ? <Palette size={11} /> : <Sparkles size={11} />}
            {kind === 'style' ? '风格' : '结构'}
          </span>
        </div>
      </div>
    </button>
  );
}
