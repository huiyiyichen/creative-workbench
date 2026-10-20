import { theme as antdTheme, type ThemeConfig } from 'antd';
import { font, palettes, radius, type CwTheme } from './tokens';

/**
 * antd 只用于表单校验、下拉、日期、上传、虚拟表格、弹层（改造方案 12.4），
 * 外观统一换成调色台配色；页面骨架与招牌组件都是自建的 cw-* 组件。
 */
export function cwAntdThemeFor(mode: CwTheme): ThemeConfig {
  const color = palettes[mode];
  const light = mode === 'light';
  return {
  algorithm: light ? antdTheme.defaultAlgorithm : antdTheme.darkAlgorithm,
  token: {
    colorPrimary: color.cy,
    colorInfo: color.bl,
    colorSuccess: color.gr,
    colorWarning: color.yl,
    colorError: color.rd,
    colorBgBase: color.base,
    colorBgContainer: color.panel,
    colorBgElevated: light ? color.panel : color.raise,
    colorBgLayout: color.base,
    colorBorder: color.line,
    colorBorderSecondary: color.grat,
    colorText: color.text,
    colorTextSecondary: color.dim,
    colorTextTertiary: color.faint,
    colorTextQuaternary: color.faint,
    fontFamily: font.sans,
    fontSize: 14,
    borderRadius: radius.md,
    borderRadiusLG: radius.lg,
    borderRadiusSM: radius.sm,
    controlHeight: 32,
    wireframe: false,
  },
  components: {
    Button: {
      primaryColor: color.onWh,
      colorPrimary: color.wh,
      colorPrimaryHover: light ? '#000000' : '#ffffff',
      colorPrimaryActive: color.text,
    },
    Modal: { contentBg: color.panel, headerBg: color.panel },
    Drawer: { colorBgElevated: color.panel },
    Tooltip: { colorBgSpotlight: color.deep },
    Table: { headerBg: color.panel, rowHoverBg: light ? 'rgba(0,0,0,0.025)' : 'rgba(255,255,255,0.02)', borderColor: color.grat },
  },
};
}

/** 兼容旧引用：暗色 */
export const cwAntdTheme: ThemeConfig = cwAntdThemeFor('dark');
