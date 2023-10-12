class BasicViewSerializerExtensions:
    extensions_expand = {'images', 'user', 'user__profile'}


class DetailViewSerializerExtensions(BasicViewSerializerExtensions):
    extensions_expand = BasicViewSerializerExtensions.extensions_expand.union({
                                                                              'tags'})
