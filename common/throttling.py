from rest_framework.throttling import ScopedRateThrottle


class SmsRateThrottle(ScopedRateThrottle):
    scope = "sms"


class AuthRateThrottle(ScopedRateThrottle):
    scope = "auth"
