export const routes=['阅读档案','特征选择','分群图谱','触达方案','回执对账'];export const page=()=>Math.min(routes.length-1,Number(location.hash.slice(1)||0));
