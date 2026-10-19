/** 地址式地区树。入库和匹配只用最后一级名称（1–20 字），路径只用于展示。 */
export type RegionNode = { name: string; children?: RegionNode[] };

export const MAX_REGIONS = 10;

export const REGION_TREE: RegionNode[] = [
  { name: "中国", children: [
    { name: "北京" }, { name: "上海" }, { name: "天津" }, { name: "重庆" },
    { name: "广东", children: [{ name: "广州" }, { name: "深圳" }, { name: "佛山" }, { name: "东莞" }, { name: "珠海" }, { name: "中山" }, { name: "惠州" }, { name: "汕头" }] },
    { name: "浙江", children: [{ name: "杭州" }, { name: "宁波" }, { name: "温州" }, { name: "嘉兴" }, { name: "金华" }] },
    { name: "江苏", children: [{ name: "南京" }, { name: "苏州" }, { name: "无锡" }, { name: "常州" }, { name: "南通" }] },
    { name: "山东", children: [{ name: "济南" }, { name: "青岛" }, { name: "烟台" }] },
    { name: "福建", children: [{ name: "福州" }, { name: "厦门" }, { name: "泉州" }] },
    { name: "四川", children: [{ name: "成都" }] },
    { name: "湖北", children: [{ name: "武汉" }] },
    { name: "湖南", children: [{ name: "长沙" }] },
    { name: "河南", children: [{ name: "郑州" }, { name: "洛阳" }] },
    { name: "安徽", children: [{ name: "合肥" }] },
    { name: "陕西", children: [{ name: "西安" }] },
    { name: "辽宁", children: [{ name: "沈阳" }, { name: "大连" }] },
    { name: "河北", children: [{ name: "石家庄" }] },
    { name: "江西", children: [{ name: "南昌" }] },
    { name: "云南", children: [{ name: "昆明" }] },
    { name: "广西", children: [{ name: "南宁" }, { name: "桂林" }] },
    { name: "海南", children: [{ name: "海口" }] },
    { name: "山西", children: [{ name: "太原" }] },
    { name: "贵州", children: [{ name: "贵阳" }] },
    { name: "黑龙江", children: [{ name: "哈尔滨" }] },
    { name: "吉林", children: [{ name: "长春" }] },
    { name: "甘肃", children: [{ name: "兰州" }] },
    { name: "内蒙古", children: [{ name: "呼和浩特" }] },
    { name: "新疆", children: [{ name: "乌鲁木齐" }] },
    { name: "西藏", children: [{ name: "拉萨" }] },
    { name: "宁夏", children: [{ name: "银川" }] },
    { name: "青海", children: [{ name: "西宁" }] },
    { name: "香港" }, { name: "澳门" },
    { name: "台湾", children: [{ name: "台北" }, { name: "高雄" }] },
  ] },
  { name: "美国", children: [
    { name: "加利福尼亚", children: [{ name: "洛杉矶" }, { name: "旧金山" }, { name: "圣何塞" }] },
    { name: "纽约州", children: [{ name: "纽约" }] },
    { name: "得克萨斯", children: [{ name: "休斯顿" }, { name: "达拉斯" }, { name: "奥斯汀" }] },
    { name: "华盛顿州", children: [{ name: "西雅图" }] },
    { name: "华盛顿特区" },
    { name: "佛罗里达", children: [{ name: "迈阿密" }] },
    { name: "伊利诺伊", children: [{ name: "芝加哥" }] },
  ] },
  { name: "加拿大", children: [
    { name: "安大略", children: [{ name: "多伦多" }, { name: "渥太华" }] },
    { name: "不列颠哥伦比亚", children: [{ name: "温哥华" }] },
    { name: "魁北克", children: [{ name: "蒙特利尔" }] },
  ] },
  { name: "英国", children: [
    { name: "英格兰", children: [{ name: "伦敦" }, { name: "曼彻斯特" }] },
    { name: "苏格兰", children: [{ name: "爱丁堡" }] },
  ] },
  { name: "德国", children: [
    { name: "巴伐利亚", children: [{ name: "慕尼黑" }] },
    { name: "柏林" }, { name: "汉堡" },
    { name: "北威", children: [{ name: "科隆" }] },
  ] },
  { name: "日本", children: [
    { name: "东京都", children: [{ name: "东京" }] },
    { name: "大阪府", children: [{ name: "大阪" }] },
    { name: "神奈川县", children: [{ name: "横滨" }] },
  ] },
  { name: "新加坡" },
  { name: "马来西亚", children: [
    { name: "吉隆坡" }, { name: "槟城" },
    { name: "柔佛", children: [{ name: "新山" }] },
  ] },
  { name: "澳大利亚", children: [
    { name: "新南威尔士", children: [{ name: "悉尼" }] },
    { name: "维多利亚", children: [{ name: "墨尔本" }] },
    { name: "昆士兰", children: [{ name: "布里斯班" }] },
  ] },
  { name: "阿联酋", children: [{ name: "迪拜" }, { name: "阿布扎比" }] },
  { name: "泰国", children: [{ name: "曼谷" }] },
  { name: "越南", children: [{ name: "胡志明市" }, { name: "河内" }] },
  { name: "印尼", children: [{ name: "雅加达" }] },
  { name: "韩国", children: [{ name: "首尔" }] },
  { name: "法国", children: [{ name: "巴黎" }] },
];

export function regionNodes(path: string[]): RegionNode[] {
  let nodes = REGION_TREE;
  for (const name of path) {
    const found = nodes.find(node => node.name === name);
    if (!found?.children) return [];
    nodes = found.children;
  }
  return nodes;
}

export function allRegionNames(nodes: RegionNode[] = REGION_TREE): string[] {
  return nodes.flatMap(node => [node.name, ...(node.children ? allRegionNames(node.children) : [])]);
}

export function regionPath(token: string): string[] {
  const walk = (nodes: RegionNode[], prefix: string[]): string[] | null => {
    for (const node of nodes) {
      const next = [...prefix, node.name];
      if (node.name === token) return next;
      const nested = node.children ? walk(node.children, next) : null;
      if (nested) return nested;
    }
    return null;
  };
  return walk(REGION_TREE, []) ?? (token ? [token] : []);
}

export function regionLabel(token: string): string {
  return regionPath(token).join(" / ");
}

export function addRegion(current: string[], path: string[]): { regions: string[]; error?: string } {
  const token = path.map(part => part.trim()).filter(Boolean).at(-1) ?? "";
  if (!token) return { regions: current, error: "先选择国家或地区" };
  if (/[，,、]/.test(token) || token.length > 20) return { regions: current, error: "一次添加一个地区，1–20 字" };
  if (current.includes(token)) return { regions: current, error: "这个地区已经添加" };
  if (current.length >= MAX_REGIONS) return { regions: current, error: "最多 10 个地区" };
  return { regions: [...current, token] };
}
