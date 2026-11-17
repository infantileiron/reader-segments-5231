/** @typedef {{id:number,code:string,weekly_reading:number,completion:number,night_share:number,note:string}} Reader */
/** @typedef {{id:number,name:string,k:number,features:string[],state:string,result:object}} Segment */
/** @typedef {{id:number,segment_id:number,cluster_id:number,title:string,note:string,members:string[],status:string,parent_outreach_id:number|null,root_outreach_id:number|null,resend_for_batch_id:number|null}} Outreach */
/** @typedef {{channel:string,serial:string,member:string,occurred_at:string,result:'delivered'|'bounced'}} ReceiptInput */
/** @typedef {{id:number,outreach_id:number,root_outreach_id:number,state:'pending'|'settled',roster:string[],roster_checksum:string,summary:object,balance_ok:boolean}} ReconBatch */
