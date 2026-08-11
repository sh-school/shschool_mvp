"""[B4-2B] القنوات الخارجية القابلة للتسليم فعلاً لمستلم بعينه.

مصدر واحد يستخدمه الطرفان: الكاتب الذي يُنشئ صفوف `NotificationDelivery`،
والعامل الذي يبحث عنها. نسختان من هذا المنطق تعنيان انحرافاً محتوماً بين ما
أنشأه الكاتب وما يطلبه العامل — والعامل يفشل مغلقاً عند النقص، فالانحراف يظهر
كإشعارٍ لا يخرج لا كخطأ يُقرأ.

Push تُعدّ قابلة للتسليم بمجرّد طلبها، بلا اشتراط وجود اشتراك: العامل نفسه
يتّخذ ذلك القرار لاحقاً ويُرجع `no_subscriptions`. اشتراطه هنا كان تغييراً في
الدلالة لا توحيداً لها.
"""


def deliverable_external_channels(user, channels):
    """القنوات المطلوبة التي يملك المستلم عنواناً لها.

    مستخدم بلا بريد لا يُرسَل له بريد، وبلا هاتف لا SMS ولا WhatsApp.
    """
    return [
        channel
        for channel, allowed in (
            ("email", "email" in channels and bool(user.email)),
            ("sms", "sms" in channels and bool(user.phone)),
            ("whatsapp", "whatsapp" in channels and bool(user.phone)),
            ("push", "push" in channels),
        )
        if allowed
    ]
