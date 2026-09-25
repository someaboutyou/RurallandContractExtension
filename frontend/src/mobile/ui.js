/**
 * Vant 组件集中出口。
 *
 * 为什么要有这个文件：
 * Vue 3 的 `<script setup>` 是按「导入名」解析模板标签的 —— import 了 `Cell`，
 * 模板里只能写 `<Cell>`，写 vant 文档惯用的 `<van-cell>` 会解析不到。
 * 这里统一取 `VanXxx` 别名，于是页面里 `import { VanCell } from "../ui.js"`
 * 之后就能写 `<van-cell>`，与 vant 官方文档保持一字不差，避免踩"组件没渲染"的坑。
 *
 * 样式（vant/lib/index.css）只在 `MobileLayout.vue` 里引入一次即可全局生效。
 * 这样 PC 端路由完全不加载 vant，不拖慢现有页面。
 */

export {
  ActionSheet as VanActionSheet,
  Button as VanButton,
  Cell as VanCell,
  CellGroup as VanCellGroup,
  Checkbox as VanCheckbox,
  CheckboxGroup as VanCheckboxGroup,
  Collapse as VanCollapse,
  CollapseItem as VanCollapseItem,
  DatePicker as VanDatePicker,
  Divider as VanDivider,
  Empty as VanEmpty,
  Field as VanField,
  Form as VanForm,
  Icon as VanIcon,
  Image as VanImage,
  List as VanList,
  Loading as VanLoading,
  NavBar as VanNavBar,
  Picker as VanPicker,
  Popup as VanPopup,
  PullRefresh as VanPullRefresh,
  Radio as VanRadio,
  RadioGroup as VanRadioGroup,
  Search as VanSearch,
  Step as VanStep,
  Steps as VanSteps,
  Switch as VanSwitch,
  Tab as VanTab,
  Tabbar as VanTabbar,
  TabbarItem as VanTabbarItem,
  Tabs as VanTabs,
  Tag as VanTag,
  Uploader as VanUploader,
} from "vant";

/** 函数式调用（Toast / Dialog / ImagePreview），直接 import 使用，不需要标签。 */
export {
  closeToast,
  showConfirmDialog,
  showDialog,
  showImagePreview,
  showToast,
} from "vant";
