### Mako defs.

<%def name="is_active(url)">
<%doc>
     Return True if the current request path is equal to ``url``.
</%doc>
    % if request.path == url:
        active
    % endif
</%def>


<%def name="form_control(field, help_text=None, label=None, label_class=None,
                         hidden=False, extra_classes=None, inline=False)">
<%doc>
    Render a Bootstrap form control around ``field``.
</%doc>
    % if inline:
        <span class="control-group ${'hidden' if hidden else ''} ${'form-inline' if inline else ''}">
             % if label:
                <label class="${label_class}"> ${label} </label>
            % endif

            ${field}

            <span class="help-inline">
                % if help_text:
                    ${help_text | n}
                % endif
                <a href="#" class="icon-warning-sign error" title="error"></a>
            </span>
        </span>
    % else:
        <div class="control-group ${'hidden' if hidden else ''}
                    % if extra_classes:
                        % for cls in extra_classes:
                            ${cls}
                        % endfor
                    % endif
                    ">

            % if label:
                <label class="control-label ${label_class}"> ${label} </label>
            % endif

            <div class="controls">
                ${field | n}
                <span class="help-inline">
                     % if help_text:
                        ${help_text | n}
                     % endif

                    <a href="#" class="icon-warning-sign error" title="error"></a>
                </span>
            </div>
        </div>
    % endif
</%def>


<%def name="datetime_control(date_name, value=None, date_label=None,
                             date_class='date input-small',
                             date_help_text=None, hour_value=None,
                             hour_label=None, hour_name='hour', hour_class='hour',
                             minute_value=None, minute_label=None,
                             minute_class='minute', minute_name='minute',
                             time_help_text=None, date_id=None)">
<%doc>
    Render a date input for ``value``, by splitting it into a date input and a
    set of hour and minute time inputs.
</%doc>
    <%
        hour = value.hour if value and hasattr(value, 'hour') else None
        minute = value.minute if value and hasattr(value, 'minute') else None
        field = h.text(date_name, value=value, class_=date_class, id=date_id)
    %>

    <div class="${date_name}_container">
     ${form_control(field, date_help_text, date_label)}
     ${time_control(hour_value if hour_value else hour,
                    minute_value if minute_value else minute,
                    hour_label, hour_name, hour_class, minute_label,
                    minute_name, minute_class, time_help_text)}
    </div>
</%def>


<%def name="time_control(hour=None, minute=None, hour_label='Time (24-hour): ',
                         hour_name='hour', hour_class='hour', minute_label=None,
                         minute_name='minute', minute_class='minute',
                         help_text=None)">
<%doc>
    Render a Bootstrap form control for a :class:`datetime.datetime` value,
    displaying only the time values (hour and minute).
</%doc>
    <div class="control-group">
        % if hour_label:
            <label class="control-label">${hour_label}</label>
        % endif

        <div class="controls">
        ${h.text(hour_label, value=hour, class_=hour_class)} : ${h.text(minute_label, value=minute, class_=minute_class)}
            <span class="help-inline">
                    % if help_text:
                    ${help_text}
                    % endif
            </span>
            <span class="help-inline">
                % if help_text:
                    ${help_text}
                % endif
            </span>
        </div>
    </div>
</%def>
