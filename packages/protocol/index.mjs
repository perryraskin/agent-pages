export const VERSION=2;
export function validateReference(value){if(!value||value.version!==VERSION||!/^[-a-z0-9]+$/.test(value.pageID)||typeof value.html!=='string')throw new Error('Invalid page reference');return value;}
