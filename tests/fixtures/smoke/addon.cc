#include <node_api.h>

static napi_value Answer(napi_env env, napi_callback_info /*info*/) {
  napi_value result;
  napi_create_int32(env, 42, &result);
  return result;
}

static napi_value Init(napi_env env, napi_value exports) {
  napi_value fn;
  napi_create_function(env, nullptr, 0, Answer, nullptr, &fn);
  napi_set_named_property(env, exports, "answer", fn);
  return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
