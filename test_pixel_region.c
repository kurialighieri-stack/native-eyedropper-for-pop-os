#include "pixel_capture.c"
#include <assert.h>
int main(void) {
 struct output formats={0};formats.format=UINT32_MAX;
 shm_format(&formats,NULL,WL_SHM_FORMAT_ABGR8888);
 shm_format(&formats,NULL,WL_SHM_FORMAT_XBGR8888);
 shm_format(&formats,NULL,WL_SHM_FORMAT_ARGB8888);
 assert(formats.format==WL_SHM_FORMAT_XBGR8888);
 shm_format(&formats,NULL,WL_SHM_FORMAT_XRGB8888);
 assert(formats.format==WL_SHM_FORMAT_XRGB8888);
 struct context mapping={0};mapping.count=2;mapping.workspace_count=2;
 mapping.groups[0].outputs=1;mapping.groups[1].outputs=2;
 mapping.workspaces[0].wl=(void*)1;mapping.workspaces[0].active=1;mapping.workspaces[0].group=&mapping.groups[0];
 mapping.workspaces[1].wl=(void*)2;mapping.workspaces[1].active=1;mapping.workspaces[1].group=&mapping.groups[1];
 assert(active_workspace(&mapping,&mapping.outputs[0])==(void*)1);
 assert(active_workspace(&mapping,&mapping.outputs[1])==(void*)2);
 mapping.workspaces[0].active=0;assert(active_workspace(&mapping,&mapping.outputs[0])==NULL);
 mapping.workspaces[1].removed=1;assert(active_workspace(&mapping,&mapping.outputs[1])==NULL);
 struct context ctx={0};ctx.count=1;
 struct output *o=&ctx.outputs[0];strcpy(o->name,"test");o->width=3;o->height=3;o->valid=1;o->format=WL_SHM_FORMAT_XRGB8888;
 uint32_t data[9]={0,1,2,3,4,5,6,7,8}, region[9], selected;o->pixels=data;
 const int expected[8][9]={{0,1,2,3,4,5,6,7,8},{6,3,0,7,4,1,8,5,2},{8,7,6,5,4,3,2,1,0},{2,5,8,1,4,7,0,3,6},{2,1,0,5,4,3,8,7,6},{8,5,2,7,4,1,6,3,0},{6,7,8,3,4,5,0,1,2},{0,3,6,1,4,7,2,5,8}};
 for(int t=0;t<8;t++) {
  o->transform=t;assert(pixel_region(&ctx,"test",.5,.5,3,region)==0);
  for(int i=0;i<9;i++)assert(region[i]==(uint32_t)expected[t][i]);
  double points[]={0,.25,.5,.99,1};
  for(int x=0;x<5;x++)for(int y=0;y<5;y++) {
   assert(pixel_read(&ctx,"test",points[x],points[y],&selected)==0);
   assert(pixel_region(&ctx,"test",points[x],points[y],3,region)==0);
   assert(region[4]==selected);
  }
 }
 assert(pixel_region(&ctx,"test",.5,.5,2,region)==-1);
 o->transform=0;o->format=WL_SHM_FORMAT_XBGR8888;data[4]=0x00123456;
 assert(pixel_region(&ctx,"test",.5,.5,3,region)==0);assert(region[4]==0x00563412);
 return 0;
}
